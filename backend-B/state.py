"""
BState — 后端 B 共享状态。
单进程多线程: 位姿字段由 pose_lock 保护 (高频 rospy 回调写,上行/目标点线程读)。
"""
import threading
import time
from dataclasses import dataclass, field


@dataclass
class PoseData:
    pos: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    quat: list = field(default_factory=lambda: [1.0, 0.0, 0.0, 0.0])  # [w,x,y,z]
    vel: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    accel: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    angular_vel: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    ts: float = 0.0


@dataclass
class IMUData:
    """富 IMU 数据 (telemetry 帧, 不入前端, 仅入库)。"""
    accel: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    angular_vel: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    ts: float = 0.0


class BState:
    """后端 B 全局状态, 所有线程共享。"""

    def __init__(self, field_config: dict, constraints: dict):
        # ── 配置 (只读, 启动后不变) ──
        self.field = field_config
        self.default_constraints = constraints

        # ── 高频位姿 (pose_lock 保护) ──
        self._pose = PoseData()
        self._last_data_ts: float = 0.0
        self._imu = IMUData()
        self.pose_lock = threading.Lock()

        # ── 目标点与动作 ──
        self.current_goal: list | None = None       # [x, y, z] 当前下发的目标点
        self.current_action_index: int = 0           # 当前执行中动作索引
        self.current_action_plan: list | None = None # 当前 ActionCommand 列表

        # ── 连接状态 ──
        self.ipc_connected: bool = False
        self.small_model_status: str = "idle"        # idle / active / error

    # ── 位姿访问器 (加锁) ──

    @property
    def current_pose(self) -> PoseData:
        with self.pose_lock:
            return self._pose

    @property
    def last_data_ts(self) -> float:
        with self.pose_lock:
            return self._last_data_ts

    def update_pose(self, pos, quat, vel, accel, angular_vel, ts):
        """rospy 回调调用, 高频写入。"""
        with self.pose_lock:
            self._pose.pos = list(pos)
            self._pose.quat = list(quat)  # [w,x,y,z]
            self._pose.vel = list(vel)
            self._pose.accel = list(accel)
            self._pose.angular_vel = list(angular_vel)
            self._pose.ts = ts
            self._last_data_ts = ts

    @property
    def current_imu(self) -> IMUData:
        with self.pose_lock:
            return self._imu

    def update_imu(self, accel, angular_vel, ts):
        with self.pose_lock:
            self._imu.accel = list(accel)
            self._imu.angular_vel = list(angular_vel)
            self._imu.ts = ts
