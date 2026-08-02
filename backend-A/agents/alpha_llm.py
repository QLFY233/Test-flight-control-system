"""
LLMTranslator — 基于 LLM 的 ActionTranslator 实现 (先导: DeepSeek)。
α 系统 prompt 从 prompts/alpha.md 加载。
"""
import asyncio
import json
import logging
import threading
from concurrent.futures import TimeoutError as FutureTimeoutError

from .translator_base import ActionTranslator, TranslateError
from bus.protocol import SCHEMA_VERSION

logger = logging.getLogger(__name__)

# ActionCommand schema for structured output validation
ACTION_COMMAND_SCHEMA = {
    "type": "object",
    "required": ["actions"],
    "properties": {
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["code"],
                "properties": {
                    "code": {
                        "type": "string",
                        "enum": [
                            "takeoff", "land", "goto", "move",
                            "climb", "descend", "yaw", "hover", "return_home",
                        ],
                    },
                    "value": {"type": "number"},
                    "target": {"type": "array", "items": {"type": "number"}},
                    "units": {"type": "string"},
                    "comment": {"type": "string"},
                },
            },
        },
        "safety_constraints": {
            "type": "object",
            "properties": {
                "speed_max": {"type": "number"},
                "ceiling": {"type": "number"},
                "floor": {"type": "number"},
            },
        },
    },
}


class LLMTranslator(ActionTranslator):
    """基于 LLM 的 α 翻译器 (先导: DeepSeek-V4-Flash/DeepSeek Chat)。

    translate() 是同步方法 (供 asyncio.to_thread 调用), 内部经一个常驻事件循环
    线程执行 Agent.run()。

    I1 背景: pydantic-ai 的 httpx AsyncOpenAI 客户端在 Agent 构造时创建并绑定
    当时的运行循环; 原实现每次调用 asyncio.run() 新建/销毁 loop, 第二次翻译时
    httpx 连接池跨循环复用 → "Event loop is closed" 类错误。
    """

    def __init__(self, agent, system_prompt: str = ""):
        self._agent = agent
        self._prompt = system_prompt
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._timeout = 60.0  # 单次 LLM 翻译上限 (s)

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        """懒启动常驻事件循环线程 (首次翻译时)。"""
        if self._loop is None:
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(
                target=self._loop.run_forever,
                name="alpha-llm-loop",
                daemon=True,
            )
            self._thread.start()
            logger.info("[alpha-llm] dedicated event loop thread started")
        return self._loop

    def translate(self, intent: str, pose: dict, env: dict) -> dict:
        """用 LLM 将指令翻译为 ActionCommand JSON (同步, 供 asyncio.to_thread 调用)。"""
        loop = self._ensure_loop()
        fut = asyncio.run_coroutine_threadsafe(
            self._translate_async(intent, pose, env), loop
        )
        try:
            return fut.result(timeout=self._timeout)
        except FutureTimeoutError:
            fut.cancel()
            raise TranslateError(f"LLM translation timed out after {self._timeout:.0f}s")

    def close(self):
        """关闭常驻事件循环线程 (α loop 停止时由 AlphaLoop 调用)。"""
        if self._loop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._loop = None
        self._thread = None
        logger.info("[alpha-llm] dedicated event loop thread stopped")

    async def _translate_async(self, intent: str, pose: dict, env: dict) -> dict:
        """用 LLM 将指令翻译为 ActionCommand JSON。"""
        # 构建用户消息 (系统 prompt 已在 Agent instructions 中)
        pos_str = (
            f"当前位置: [{pose.get('pos', [0,0,0])[0]:.2f}, "
            f"{pose.get('pos', [0,0,1])[1]:.2f}, "
            f"{pose.get('pos', [0,0,0])[2]:.2f}]"
        )
        user_prompt = f"{pos_str}\n指令: {intent}\n请输出 ActionCommand JSON:"

        try:
            # Pydantic AI Agent.run() — 非流式, instructions 已在构造时注入
            result = await self._agent.run(user_prompt)
            text = result.output if isinstance(result.output, str) else str(result.output)

            # 提取 JSON (处理 markdown 代码块包裹)
            action_cmd = self._extract_json(text)

            # 验证必含 actions
            if "actions" not in action_cmd or not action_cmd["actions"]:
                raise TranslateError("LLM output missing 'actions' field")

            # 注入 schema_version 与 task_id
            import time
            action_cmd["schema_version"] = SCHEMA_VERSION
            if "task_id" not in action_cmd:
                action_cmd["task_id"] = time.strftime("%Y%m%d%H%M%S")

            # 验证动作编码合法性
            valid_codes = {
                "takeoff", "land", "goto", "move",
                "climb", "descend", "yaw", "hover", "return_home",
            }
            for a in action_cmd["actions"]:
                if a.get("code") not in valid_codes:
                    raise TranslateError(f"Unknown action code: {a.get('code')}")

            logger.info(f"[alpha-llm] translated: {len(action_cmd['actions'])} actions")
            return action_cmd

        except TranslateError:
            raise
        except Exception as e:
            logger.error(f"[alpha-llm] LLM translation failed: {e}")
            raise TranslateError(f"LLM call failed: {e}")

    @staticmethod
    def _extract_json(text: str) -> dict:
        """从 LLM 输出中提取 JSON (处理 markdown 代码块)。"""
        text = text.strip()
        # 去掉 ```json ... ``` 包裹
        if text.startswith("```"):
            lines = text.split("\n")
            # 去掉首行 ```json 和末行 ```
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        return json.loads(text)
