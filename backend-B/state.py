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
        # 初值取启动时刻 (wall time): 避免 monitor 启动即把 0.0 判为停产 (B-5)
        self._last_data_ts: float = time.time()
        self._data_received: bool = False  # 是否已收到首帧无人机数据 (monitor 首帧前不评估)
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
        # 注意: 返回内部对象引用 (非一致快照语义)。读侧在锁外取 pos/vel 等多字段时,
        # 可能读到 "新 pos + 旧 ts" 的混合快照; 单字段赋值原子、无撕裂写, 可接受。
        # 如需强一致快照请自行在锁内复制 (B-18)。
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
            # 停产判定用 wall time 统一时钟源 (B-10), 避免 ROS header stamp 与 wall clock 错配
            self._last_data_ts = time.time()
            self._data_received = True

    @property
    def current_imu(self) -> IMUData:
        with self.pose_lock:
            return self._imu

    @property
    def data_received(self) -> bool:
        """是否已收到首帧无人机数据 (monitor 据此跳过启动假阳性评估, B-5)。"""
        with self.pose_lock:
            return self._data_received

    def update_imu(self, accel, angular_vel, ts):
        """IMU 回调 — 单次加锁同时写富 IMU (telemetry) 与 _pose 的 accel/angular_vel (pose 上行)。
        注意: 调用方不得再持有 pose_lock 调本方法 (非重入锁, 见 B-1 死锁修复)。"""
        with self.pose_lock:
            self._imu.accel = list(accel)
            self._imu.angular_vel = list(angular_vel)
            self._imu.ts = ts
            # 与 pose 上行字段对齐 (run_b.py 之前只写 _imu, 导致上行 accel/angularVel 恒零, B-2)
            self._pose.accel = list(accel)
            self._pose.angular_vel = list(angular_vel)
            self._data_received = True
