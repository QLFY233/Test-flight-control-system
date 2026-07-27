"""
AppState — 后端 A 共享状态。
asyncio.Lock 保护; 高频位姿单独锁。
"""
import asyncio
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Config:
    """A 侧配置 (从 config_loader 加载)。"""
    alpha_loop_period: float = 2.0
    alpha_history_rounds: int = 10
    field_cfg: dict = field(default_factory=dict)
    constraints: dict = field(default_factory=dict)


@dataclass
class PoseData:
    pos: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    quat: list[float] = field(default_factory=lambda: [1.0, 0.0, 0.0, 0.0])
    vel: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    accel: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    angular_vel: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    ts: float = 0.0
    updated_at: float = 0.0


@dataclass
class ActionPlan:
    """α 产出的 ActionCommand 序列。"""
    task_id: str = ""
    actions: list[dict] = field(default_factory=list)
    safety_constraints: dict = field(default_factory=dict)
    action_index: int = 0

    def has_remaining(self) -> bool:
        return self.action_index < len(self.actions)

    def next_action(self) -> dict | None:
        if not self.has_remaining():
            return None
        a = self.actions[self.action_index]
        self.action_index += 1
        return a


class AppState:
    """后端 A 全局状态, 单实例。"""

    def __init__(self, config: Config):
        self.config = config

        # ── 会话 ──
        self.session_id: str | None = None

        # ── 位姿 (高频单独锁) ──
        self._pose = PoseData()
        self._pose_lock = asyncio.Lock()

        # ── α 相关 ──
        self.alpha_input_queue: list[str] = []
        self.current_action_plan: ActionPlan | None = None
        self.pending_proposal: Any | None = None       # β propose 待审核
        self.last_human_message_to_beta: str | None = None
        self.last_intent: dict | None = None            # α 最近产出的 ActionCommand

        # ── β 相关 ──
        self.last_pong_at: float = 0.0

        # ── 连接状态 ──
        self.ipc_connected: bool = False
        self.flight_status: str = "idle"

        # ── 环境 ──
        self.current_environment: dict | None = None
        self.environment_id: int | None = None

        # ── LLM 状态 ──
        self.last_llm_call_ok: bool = True

        # ── 通用锁 (低频操作) ──
        self._lock = asyncio.Lock()

    # ── 位姿访问器 ──

    @property
    def current_pose(self) -> PoseData:
        return self._pose

    async def update_pose(self, pos, quat, vel, accel, angular_vel, ts):
        async with self._pose_lock:
            self._pose.pos = list(pos)
            self._pose.quat = list(quat)
            self._pose.vel = list(vel)
            self._pose.accel = list(accel)
            self._pose.angular_vel = list(angular_vel)
            self._pose.ts = ts
            self._pose.updated_at = time.time()

    # ── α 队列 ──

    async def drain_alpha_input_queue(self) -> list[str]:
        """取出并清空 α 输入队列。"""
        async with self._lock:
            items = self.alpha_input_queue[:]
            self.alpha_input_queue.clear()
            return items

    async def push_alpha_input(self, text: str):
        """向 α 输入队列末尾追加。"""
        async with self._lock:
            self.alpha_input_queue.append(text)
