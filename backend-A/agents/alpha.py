"""
α Agent — 非对话动作翻译器 + loop 仲裁。
α 不与人对话: 接收 β 转发 / 人确认的指令 → 翻译为 ActionCommand → 下发 B 侧 small_model。
"""

import os
import asyncio
import logging

from .translator_base import ActionTranslator, TranslateError
from .alpha_llm import LLMTranslator
from .llm import make_agent
from bus import router as bus_router
from bus.protocol import (
    TO_SMALL_MODEL, CALL_TOOL_ACTION, CALL_TOOL_HOVER,
    FLIGHT_STATUS_EXECUTING, FLIGHT_STATUS_HOVERING,
    MSG_TYPE_ERROR,
)

logger = logging.getLogger(__name__)


def _load_alpha_prompt() -> str:
    """加载 α 系统 prompt。"""
    prompt_path = os.path.join(os.path.dirname(__file__), "..", "prompts", "alpha.md")
    try:
        with open(prompt_path, "r") as f:
            return f.read()
    except FileNotFoundError:
        logger.warning(f"[alpha] prompt file not found at {prompt_path}, using built-in")
        return _BUILTIN_PROMPT


_BUILTIN_PROMPT = """\
你是一个试飞控制系统动作翻译器（α Agent）。将飞行指令翻译为 ActionCommand JSON。
只输出 JSON，不要对话。"""


def make_translator() -> ActionTranslator:
    """创建 α 翻译器 (按 ALPHA_BACKEND 环境变量)。

    ALPHA_BACKEND=llm (默认, 先导) → LLMTranslator (DeepSeek)
    ALPHA_BACKEND=small (远期) → 蒸馏小模型 α
    """
    backend = os.environ.get("ALPHA_BACKEND", "llm")
    if backend == "llm":
        prompt = _load_alpha_prompt()
        agent = make_agent(instructions=prompt)
        return LLMTranslator(agent=agent, system_prompt=prompt)
    elif backend == "small":
        raise NotImplementedError("Small model α not yet implemented (stage M)")
    else:
        raise ValueError(f"Unknown ALPHA_BACKEND: {backend}")


class AlphaLoop:
    """α loop — 周期性从队列取指令, 翻译为 ActionCommand, 发 B 侧 small_model。

    仲裁逻辑 (总体架构 §2.3):
    1. 若 α 输入队列非空 → 翻译新指令 (打断预设)
    2. elif 执行中预设还有未完成动作 → 继续下发
    3. else → 下发 hover (安全默认)
    """

    def __init__(self, state, translator: ActionTranslator):
        self._state = state
        self._translator = translator
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self):
        """启动 α loop。"""
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(f"[alpha] loop started, period={self._state.config.alpha_loop_period}s")

    async def stop(self):
        """停止 α loop。"""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        # 最后发一次 hover
        try:
            await self._send_hover()
        except Exception:
            pass
        # I1: 关闭 LLM 常驻事件循环线程 (若翻译器支持)
        if self._translator is not None and hasattr(self._translator, "close"):
            try:
                self._translator.close()
            except Exception:
                pass
        logger.info("[alpha] loop stopped")

    async def _loop(self):
        """主循环。"""
        period = self._state.config.alpha_loop_period
        backoff = 1.0  # 退避初始值

        while self._running:
            try:
                await self._tick()
                if not self._state.last_llm_call_ok:
                    self._state.last_llm_call_ok = True
                    await self._broadcast_llm_status("up")
                backoff = 1.0  # 成功后重置退避
            except Exception as e:
                logger.error(f"[alpha] tick error: {e}, backoff={backoff}s")
                self._state.last_llm_call_ok = False
                await self._send_hover()
                await self._broadcast_llm_status("error", str(e))
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 5.0)  # 退避 1→2→4→5s
                continue

            await asyncio.sleep(period)

    async def _tick(self):
        """单次 tick: 仲裁 → 翻译 → 下发。"""
        # 1. 从输入队列取指令
        inputs = await self._state.drain_alpha_input_queue()

        if inputs:
            # 有新指令 → 翻译 (打断预设)
            intent = " ".join(inputs)
            logger.info(f"[alpha] processing input: {intent[:80]}...")
            action_cmd = await self._translate(intent)
            # N6: 计划改用类型化 ActionPlan (原裸 dict, 死代码 dataclass 复活)
            from state import ActionPlan
            self._state.current_action_plan = ActionPlan(
                task_id=action_cmd.get("task_id", ""),
                actions=action_cmd.get("actions", []),
                safety_constraints=action_cmd.get("safety_constraints", {}),
            )
            self._state.last_intent = action_cmd
            await self._dispatch_action(action_cmd)
            # 训练标的: 记录成功翻译 + 下发 (metadata 含 approved/path/action_code)
            await self._log_action(action_cmd, "forward")
        elif self._state.current_action_plan and self._state.current_action_plan.actions:
            # 预设未完成 → 继续 (B 侧 small_model 管动作推进)
            pass
        else:
            # 无任务 → 安全悬停
            await self._send_hover()

    async def _translate(self, intent: str) -> dict:
        """翻译指令为 ActionCommand (用 asyncio.to_thread 防止 LLM 阻塞事件循环)。"""
        pose = {
            "pos": self._state.current_pose.pos,
            "quat": self._state.current_pose.quat,
            "vel": self._state.current_pose.vel,
        }
        env = {}  # 先导为空

        try:
            # LLM 调用耗时 1~5s, 用 to_thread 避免阻塞心跳
            action_cmd = await asyncio.to_thread(
                self._translator.translate, intent, pose, env
            )
            return action_cmd
        except TranslateError as e:
            # S3: hover 去重 — 由 _loop 的 except 统一兜底, 此处不再重复发送
            logger.warning(f"[alpha] translation failed: {e}")
            raise
        except Exception as e:
            logger.error(f"[alpha] unexpected translation error: {e}")
            raise TranslateError(str(e))

    async def _dispatch_action(self, action_cmd: dict):
        """将 ActionCommand 下发 B 侧 small_model (经 A↔B IPC bridge)。"""
        try:
            result = await bus_router.call(
                to=TO_SMALL_MODEL,
                tool=CALL_TOOL_ACTION,
                args={"action": action_cmd},
                _from="alpha",
            )
            payload = result.get("payload", {})
            # B1: IPC 先导 fire-and-forget 只回 ack; B 断开/组件错误时 router 吞异常返回
            # msg_type=error。必须显式校验, 否则被误报为 executing → 状态机卡死永不回退。
            if (
                result.get("msg_type") == MSG_TYPE_ERROR
                or payload.get("status") == "error"
                or payload.get("error")
            ):
                detail = (
                    payload.get("error")
                    or payload.get("status")
                    or result.get("msg_type")
                    or "unknown"
                )
                logger.error(f"[alpha] dispatch to B failed: {detail}")
                self._state.last_llm_call_ok = False
                await self._send_hover()
                return
            if payload.get("status") == "rejected":
                reason = payload.get("reason", "unknown")
                logger.warning(f"[alpha] small_model rejected: {reason}")
                await self._send_hover()
                return
            self._state.flight_status = FLIGHT_STATUS_EXECUTING
            logger.info("[alpha] action dispatched to small_model")
            # 🟡-3: 广播 α 产出到前端 WS (spec §5 注: 动作编码 + 目标点)
            await self._broadcast_alpha_output(action_cmd)
        except Exception as e:
            logger.error(f"[alpha] dispatch to B failed: {e}")
            self._state.last_llm_call_ok = False
            await self._send_hover()

    async def _send_hover(self):
        """下发安全悬停。"""
        self._state.flight_status = FLIGHT_STATUS_HOVERING
        try:
            await bus_router.call(
                to=TO_SMALL_MODEL,
                tool=CALL_TOOL_HOVER,
                args={},
                _from="alpha",
            )
        except Exception as e:
            logger.warning(f"[alpha] hover dispatch failed: {e}")

    async def emergency_hover(self):
        """B 侧 reject 时由 bridge 调用 (🟡-6) — 安全默认: 清计划 + 悬停。"""
        self._state.current_action_plan = None
        await self._send_hover()

    async def _broadcast_alpha_output(self, action_cmd: dict):
        """推送 α 产出 (动作序列 + 目标点) 到前端 WS (🟡-3)。"""
        try:
            from web.ws import broadcast_alpha_output
            actions = action_cmd.get("actions", [])
            goal = None
            for a in reversed(actions):
                if a.get("target"):
                    goal = a["target"]
                    break
            await broadcast_alpha_output(action_cmd, goal, actions)
        except Exception:
            pass

    async def _broadcast_llm_status(self, state: str, detail: str = ""):
        """推送 LLM 链路状态到前端 WS。"""
        try:
            from web.ws import broadcast_link_status
            await broadcast_link_status("llm", state, detail if detail else None)
        except Exception:
            pass

    async def _log_action(self, action_cmd: dict, path: str):
        """记录 α 翻译结果到 conversations 表 (训练标的)。

        metadata 含:
          - approved: True (forward 免审 / propose 人已审)
          - path: "forward" | "propose"
          - action_code: 动作编码列表
          - schema_version: 2
        """
        try:
            if not self._state.session_id:
                # N8: 细粒度 session id — 秒级会令同一秒内两条指令共享 id (会话混淆)
                import time as _time
                self._state.session_id = (
                    _time.strftime("%Y%m%d%H%M%S")
                    + f"{_time.time_ns() % 100_000:05d}"
                )

            from db.repos import save_conversation, create_session as _create_session
            from db.repos import get_session as _get_session
            from db.session import async_session as _db_sess
            import json as _json

            actions = action_cmd.get("actions", [])
            codes = [a.get("code", "") for a in actions]

            # 任务自动命名 (#3): propose 的 pending_task_name 优先;
            # forward 路径 (无提议) 从动作序列生成结构化摘要
            # (对齐 beta_tools._derive_task_name: 起飞1m→飞往(3,2)→悬停2s…)
            from tools.beta_tools import _derive_task_name
            task_name = (
                getattr(self._state, "pending_task_name", None)
                or _derive_task_name(None, actions)
            )

            async with _db_sess() as session:
                # N8: 显式建 session 行 — 此前全仓无 create_session 调用,
                # conversations/telemetry 全是孤儿行 (FK 悬空)
                existing = await _get_session(session, self._state.session_id)
                if existing is None:
                    await _create_session(
                        session,
                        self._state.session_id,
                        task_desc=task_name,
                    )
                elif task_name and not existing.task_description:
                    # 会话先由对话创建 (task_desc=None) → 补名
                    existing.task_description = task_name
                    await session.commit()
                    logger.info(f"[alpha] task named: {task_name}")

                await save_conversation(
                    session,
                    session_id=self._state.session_id,
                    agent="alpha",
                    role="tool_call",
                    content=_json.dumps(action_cmd, ensure_ascii=False),
                    metadata={
                        "approved": True,
                        "path": path,
                        "action_code": codes,
                        "schema_version": 2,
                        "task_id": action_cmd.get("task_id", ""),
                    },
                )
            logger.info(f"[alpha] action logged: {codes} (path={path})")
        except Exception as e:
            logger.warning(f"[alpha] log_action failed: {e}")
