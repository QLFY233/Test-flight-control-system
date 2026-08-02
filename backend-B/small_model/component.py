"""
small_model 组件入口 — 处理 generate_goal / abort / hover。
经 B 内总线调用, 产出目标点缓存供 rosbridge publisher 线程消费。
"""
from __future__ import annotations
import math
import time
import logging
import threading

from .action_codes import VALID_ACTION_CODES
from .goal_gen import make_goal_generator, GoalGenError
from bus.protocol import (
    SCHEMA_VERSION,
    EVENT_TOOL_REJECT,
    EVENT_TOOL_STATUS,
    FLIGHT_STATUS_EXECUTING,
    FLIGHT_STATUS_COMPLETED,
    FLIGHT_STATUS_HOVERING,
    TO_ALPHA,
    REJECT_UNKNOWN_ACTION_CODE,
    REJECT_OUT_OF_BOUNDARY,
    REJECT_EGO_PLANNER_UNREACHABLE,
)

logger = logging.getLogger(__name__)


def yaw_from_quat(quat: list) -> float:
    """从 quaternion [w,x,y,z] 提取 yaw 角 (rad)。可用于外部模块。"""
    w, x, y, z = quat[0], quat[1], quat[2], quat[3]
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


class SmallModelComponent:
    """small_model 总线组件 (总体架构 §3.7)。"""

    def __init__(self, state):
        self._state = state
        self._generator = make_goal_generator()
        # 注入 home 位置给 stub
        home = state.field.get("home", {}).get("position", [0, 0, 0.5])
        self._generator._home = home
        # 当前目标缓存
        self._lock = threading.Lock()
        self._current_goal: dict | None = None
        # 当前 ActionCommand 的合并后安全约束 (跨动作推进保留)
        self._merged_safety: dict | None = None
        # 事件发送回调 (由 lifecycle 注入, 用于上行 reject/status)
        self._send_event = None
        # B-6: 状态锁 — 保护 current_action_plan/current_action_index/small_model_status/
        # _merged_safety/_current_goal 的跨线程一致性 (IPC 线程 vs goal-publisher 线程)。
        # 所有修改路径 (generate/abort/hover/advance) 必须在同一临界区完成,
        # 否则新计划写入与 publisher 推进之间会竞态 (新计划首条动作被跳过)。

    def set_event_sender(self, sender):
        """注入事件发送回调: send_event(msg: dict)。"""
        self._send_event = sender

    def handle(self, tool: str, args: dict) -> dict:
        """B 内总线 handle 入口。"""
        if tool == "generate_goal":
            return self._handle_generate_goal(args)
        elif tool == "abort":
            return self._handle_abort(args)
        elif tool == "hover":
            return self._handle_hover(args)
        else:
            return {"status": "error", "reason": f"unknown tool: {tool}"}

    def _handle_generate_goal(self, args: dict) -> dict:
        """收到 A 下发的 action call — 解析 ActionCommand, 生成目标点。"""
        action_cmd = args.get("action", {})
        if not action_cmd:
            return {"status": "error", "reason": "missing 'action' in args"}

        actions = action_cmd.get("actions", [])
        overrides = action_cmd.get("safety_constraints", {})
        if not actions:
            logger.warning("[small_model] generate_goal with empty actions list")
            return {"status": "error", "reason": "empty actions list"}

        # B-6: 计划写入 + 首条动作翻译在同一临界区, 防止 publisher 线程用旧目标推进新计划
        with self._lock:
            self._merged_safety = self._merge_safety(overrides)
            self._state.current_action_plan = actions
            self._state.current_action_index = 0
            self._state.small_model_status = "executing"
            return self._generate_next_goal()

    def _generate_next_goal(self) -> dict:
        """从 current_action_plan 取当前未执行的动作并翻译为目标点。
        注意: 假定调用方已持有 self._lock (B-6 锁纪律), 不得在外部无锁调用。"""
        idx = self._state.current_action_index
        actions = self._state.current_action_plan or []

        if idx >= len(actions):
            self._state.small_model_status = "idle"
            self._send_status(FLIGHT_STATUS_COMPLETED, idx, len(actions))
            self._current_goal = None
            return {"status": "ok", "note": "all actions completed"}

        action = actions[idx]
        code = action.get("code", "")

        if code not in VALID_ACTION_CODES:
            self._state.small_model_status = "idle"
            # 🟡-5: reason 用冻结常量, 编码信息附 detail
            self._send_reject(REJECT_UNKNOWN_ACTION_CODE, idx, detail=f"unknown action code: {code}")
            self._current_goal = None
            return {"status": "rejected", "reason": REJECT_UNKNOWN_ACTION_CODE}

        safety = self._merged_safety or self._merge_safety({})

        try:
            pose = {
                "pos": self._state.current_pose.pos[:],
                "quat": self._state.current_pose.quat[:],
                "vel": self._state.current_pose.vel[:],
                "yaw": yaw_from_quat(self._state.current_pose.quat),
            }
        except Exception:
            pose = {"pos": [0, 0, 0.5], "quat": [1, 0, 0, 0], "vel": [0, 0, 0], "yaw": 0.0}

        env = {}  # 先导 env 为空 (阶段4 填离散环境)
        try:
            goal = self._generator.generate(action, pose, env, safety)
        except GoalGenError as e:
            reason = str(e)
            base, detail = self._normalize_reject(reason)
            self._state.small_model_status = "idle"
            self._send_reject(base, idx, detail=detail)
            self._current_goal = None
            return {"status": "rejected", "reason": base}

        self._current_goal = goal
        self._send_status(FLIGHT_STATUS_EXECUTING, idx + 1, len(actions))
        return {"status": "ok", "goal": goal}

    def _advance_action(self) -> bool:
        """切下一条动作。返回 True 表示还有剩余动作。
        注意: 假定调用方已持有 self._lock (B-6), index+=1 与读 plan 必须同一临界区。"""
        self._state.current_action_index += 1
        idx = self._state.current_action_index
        actions = self._state.current_action_plan or []
        if idx >= len(actions):
            self._state.small_model_status = "idle"
            self._current_goal = None
            self._send_status(FLIGHT_STATUS_COMPLETED, len(actions), len(actions))
            return False
        # 生成下一条动作的目标点 (复用 _merged_safety)
        self._generate_next_goal()
        return True

    def _handle_abort(self, args: dict) -> dict:
        """中止当前动作序列, 切悬停。"""
        with self._lock:
            self._state.current_action_plan = None
            self._state.current_action_index = 0
            self._state.small_model_status = "idle"
            self._merged_safety = None
            self._current_goal = None
        logger.warning("[small_model] abort — clearing action plan, hovering")
        return {"status": "ok", "action": "abort"}

    def _handle_hover(self, args: dict) -> dict:
        """安全悬停 — 目标点 = 当前位置。"""
        with self._lock:
            self._state.current_action_plan = None
            self._state.current_action_index = 0
            self._state.small_model_status = FLIGHT_STATUS_HOVERING
            self._merged_safety = None
            try:
                p = self._state.current_pose
                goal = {"goal": p.pos[:], "yaw": yaw_from_quat(p.quat), "speed_max": 1.5}
            except Exception:
                goal = {"goal": [0, 0, 0.5], "yaw": 0.0, "speed_max": 1.5}
            self._current_goal = goal
            self._send_status(FLIGHT_STATUS_HOVERING, 0, 0)
        logger.info("[small_model] hover — maintaining current position")
        return {"status": "ok", "action": "hover", "goal": goal}

    def get_current_goal(self) -> dict | None:
        """目标点线程读取当前目标点 (线程安全)。"""
        with self._lock:
            return dict(self._current_goal) if self._current_goal else None

    def check_arrival_and_advance(self, pos: list, threshold: float = 0.15) -> bool:
        """检查是否到达当前目标点, 到达则自动切下条动作。返回 True 表示到达。"""
        goal = self.get_current_goal()
        if not goal:
            return False
        g = goal["goal"]
        dx = pos[0] - g[0]
        dy = pos[1] - g[1]
        dz = pos[2] - g[2]
        dist = (dx * dx + dy * dy + dz * dz) ** 0.5
        if dist < threshold:
            # B-6: 状态判定与推进在同一临界区 (get_current_goal 已释放锁, 无嵌套获取)
            with self._lock:
                # 悬停态不变
                if self._state.small_model_status == FLIGHT_STATUS_HOVERING:
                    return True
                return self._advance_action()
        return False

    # ── helpers ──

    def _normalize_reject(self, reason: str) -> tuple:
        """把 stub/GoalGenError 错误消息规范化为 (冻结 reason, detail)。
        兼容三种形式: 纯常量 / "常量:附加信息" / 未知字符串 (原样返回)。"""
        for prefix in (REJECT_UNKNOWN_ACTION_CODE, REJECT_OUT_OF_BOUNDARY, REJECT_EGO_PLANNER_UNREACHABLE):
            if reason == prefix:
                return prefix, ""
            if reason.startswith(prefix + ":"):
                return prefix, reason
        return reason, ""

    def _merge_safety(self, overrides: dict) -> dict:
        """合并默认约束与 ActionCommand 随附约束。"""
        gc = self._state.default_constraints.get("global", {})
        return {
            "speed_max": overrides.get("speed_max", gc.get("speed_max", 1.5)),
            "ceiling": overrides.get("ceiling", gc.get("ceiling", 2.5)),
            "floor": overrides.get("floor", gc.get("floor", 0.3)),
            "boundary": overrides.get("boundary") or [
                [self._state.field["boundary"]["x"][0], self._state.field["boundary"]["y"][0], self._state.field["boundary"]["z"][0]],
                [self._state.field["boundary"]["x"][1], self._state.field["boundary"]["y"][1], self._state.field["boundary"]["z"][1]],
            ],
        }

    def _send_reject(self, reason: str, action_index: int, detail: str = ""):
        """上行 reject 事件。reason 必须为冻结枚举值 (🟡-5), 附加信息放 detail。"""
        if self._send_event:
            self._send_event({
                "schema_version": SCHEMA_VERSION,
                "from": "small_model",
                "to": TO_ALPHA,
                "msg_type": "event",
                "call_id": "",
                "tool": EVENT_TOOL_REJECT,
                "args": {},
                "payload": {"reason": reason, "actionIndex": action_index, "detail": detail},
                "ts": time.time(),
            })

    def _send_status(self, flight_status: str, current_action: int, total_actions: int):
        if self._send_event:
            self._send_event({
                "schema_version": SCHEMA_VERSION,
                "from": "small_model",
                "to": TO_ALPHA,
                "msg_type": "event",
                "call_id": "",
                "tool": EVENT_TOOL_STATUS,
                "args": {},
                "payload": {
                    "flightStatus": flight_status,
                    "mode": "auto",
                    "currentAction": current_action,
                    "totalActions": total_actions,
                    "taskId": "",
                },
                "ts": time.time(),
            })
