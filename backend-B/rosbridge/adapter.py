"""
ROS 消息适配器 — 阶段抽象 (Phase1/Phase2)。
只改配置/前缀, 不动 small_model 上层 (PX4-阶段2-design.md §5)。

Phase1: sim-drone 假无人机 (/drone 前缀, PoseStamped setpoint)
Phase2: PX4 SITL + MAVROS (/mavros 前缀, PositionTarget + offboard 状态机)

坐标系: BState/A/前端/field.yaml 保持 ENU (x东 y北 z上);
NED↔ENU 变换单点收敛于此模块与 subscriber 注入点 (design §4.3)。
"""
from __future__ import annotations
import math
import os
import time
import threading
import logging
import rospy
from geometry_msgs.msg import PoseStamped, Twist, Point, Quaternion, Vector3

from .topics import get_topics, get_phase2_topics, PHASE1_PREFIX, PHASE2_PREFIX

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════
# NED ↔ ENU 变换 (单点收敛, PX4-阶段2-design.md §4.3)
# NED: x北 y东 z下 ; ENU: x东 y北 z上
# ══════════════════════════════════════════════════════════════════

def enu_to_ned(x, y, z):
    """ENU 坐标 → NED 坐标: (x,y,z) → (y, x, -z)。"""
    return (y, x, -z)


def ned_to_enu(x, y, z):
    """NED 坐标 → ENU 坐标: 与 enu_to_ned 同构 (交换 x/y + z 取反)。"""
    return (y, x, -z)


def enu_yaw_to_ned(yaw):
    """ENU yaw (从东逆时针) → NED yaw (从北顺时针): yaw_ned = π/2 - yaw_enu。"""
    return math.pi / 2.0 - yaw


def ned_yaw_to_enu(yaw):
    """NED yaw → ENU yaw (逆变换同构)。"""
    return math.pi / 2.0 - yaw


def ned_quat_to_enu_quat(q):
    """NED 系四元数 [w,x,y,z] → ENU 系四元数。

    阶段2 机动为水平飞行 (roll≈0, pitch≈0), 仅 yaw 有意义:
    yaw_enu = π/2 - yaw_ned (design §4.3), 直接重构造 yaw-only 四元数。
    非水平机动 (翻滚/俯冲) 需完整 DCM 相似变换, 阶段2 不涉及, 留待阶段4。
    """
    w, x, y, z = q
    yaw_ned = math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
    yaw_enu = ned_yaw_to_enu(yaw_ned)
    half = yaw_enu / 2.0
    return [math.cos(half), 0.0, 0.0, math.sin(half)]


def _yaw_to_quat_msg(yaw: float) -> Quaternion:
    """yaw (rad) → geometry_msgs/Quaternion (x,y,z,w 顺序)。"""
    half = yaw / 2.0
    return Quaternion(x=0.0, y=0.0, z=math.sin(half), w=math.cos(half))


# ══════════════════════════════════════════════════════════════════
# SetpointAdapter ABC
# ══════════════════════════════════════════════════════════════════

class SetpointAdapter:
    """setpoint 下发抽象 — 阶段切换只改 PHASE 环境变量 (design §5.1)。"""

    def publish_position(self, pos: list, yaw: float):
        """下发位置 setpoint (入参为 ENU 坐标/yaw)。"""
        raise NotImplementedError

    def publish_velocity(self, vel: list):
        """下发速度 setpoint (入参为 ENU)。"""
        raise NotImplementedError

    def preflight(self, timeout: float = 60.0) -> bool:
        """起飞前准备 (阶段2: offboard 状态机推进; 阶段1: 恒真)。"""
        return True

    def emergency_land(self):
        """安全兜底 (阶段2: AUTO.LAND; 阶段1: 无操作, 停发即悬停)。"""
        pass


class Phase1Adapter(SetpointAdapter):
    """阶段1 假无人机适配器 — /drone 前缀, PoseStamped setpoint。"""

    def __init__(self, prefix: str = PHASE1_PREFIX):
        topics = get_topics(prefix)
        self._pose_pub = rospy.Publisher(
            topics["setpoint_position"], PoseStamped, queue_size=10
        )
        self._vel_pub = rospy.Publisher(
            topics["setpoint_velocity"], Twist, queue_size=10
        )
        logger.info(f"[rosbridge] Phase1Adapter initialized, prefix={prefix}")

    def publish_position(self, pos: list, yaw: float):
        """下发位置 setpoint (PoseStamped, ENU 原样)。"""
        msg = PoseStamped()
        msg.header.stamp = rospy.Time.now()
        msg.header.frame_id = "map"
        msg.pose.position = Point(x=pos[0], y=pos[1], z=pos[2])
        msg.pose.orientation = _yaw_to_quat_msg(yaw)
        self._pose_pub.publish(msg)

    def publish_velocity(self, vel: list):
        """下发速度 setpoint (Twist)。"""
        msg = Twist()
        msg.linear = Vector3(x=vel[0], y=vel[1], z=vel[2])
        self._vel_pub.publish(msg)


class Phase2Adapter(SetpointAdapter):
    """阶段2 PX4 SITL 适配器 — /mavros 前缀, PositionTarget + offboard 状态机。

    offboard 状态机 (design §5.2):
        DISARMED → STREAMING(20Hz 当前位置 setpoint ≥3s) → ARMING → OFFBOARD → ACTIVE
    ARM 前置: 连续 stream ≥3s + 距 home < 2m + state.connected (design §7)。
    abort/land 兜底: emergency_land() → set_mode AUTO.LAND (design §5.3)。
    """

    # type_mask 位置控制 (design §4.2): 忽略速度/加速度/力/yaw_rate, 使用 yaw
    TYPE_MASK_POSITION = 0

    def __init__(self, prefix: str = PHASE2_PREFIX, home: list = None):
        from mavros_msgs.msg import PositionTarget, State
        from mavros_msgs.srv import CommandBool, SetMode

        self._msg_cls = PositionTarget
        self._state_cls = State
        self._arm_srv = CommandBool
        self._set_mode_srv = SetMode

        topics = get_phase2_topics(prefix)
        self._setpoint_pub = rospy.Publisher(
            topics["setpoint_raw"], PositionTarget, queue_size=10
        )
        self._home = list(home) if home else [0.0, 0.0, 0.5]
        self._lock = threading.Lock()
        self._phase = "DISARMED"          # 状态机当前阶段
        self._mav_connected = False
        self._mav_armed = False
        self._mav_mode = ""
        self._stream_count = 0            # STREAMING 已发帧数
        self._offboard_lost_at = None     # 非主动切出 OFFBOARD 的时刻
        self._emergency = False           # 已触发应急降落

        self._state_sub = rospy.Subscriber(
            topics["state"], State, self._on_mav_state
        )
        # 服务代理延迟创建 (等 rospy 服务出现)
        self._arm_proxy = None
        self._mode_proxy = None
        self._px, self._py, self._pz = 0.0, 0.0, 0.5
        self._yaw = 0.0
        logger.info(f"[rosbridge] Phase2Adapter initialized, prefix={prefix}, home={self._home}")

    # ── 状态输入 ──
    def _on_mav_state(self, msg):
        with self._lock:
            self._mav_connected = bool(msg.connected)
            self._mav_armed = bool(msg.armed)
            self._mav_mode = msg.mode or ""
            if self._mav_connected:
                self._px, self._py, self._pz = (
                    msg.header.stamp.to_sec(), 0.0, 0.0  # 占位, 位姿由 subscriber 负责
                )

    def _snapshot(self):
        with self._lock:
            return dict(
                connected=self._mav_connected, armed=self._mav_armed,
                mode=self._mav_mode, phase=self._phase,
                offboard_lost_at=self._offboard_lost_at,
            )

    # ── setpoint 下发 ──
    def publish_position(self, pos: list, yaw: float):
        """下发位置 setpoint (入参 ENU; 内部 ENU→NED + PositionTarget)。"""
        nx, ny, nz = enu_to_ned(pos[0], pos[1], pos[2])
        yaw_ned = enu_yaw_to_ned(yaw)
        msg = self._msg_cls()
        msg.header.stamp = rospy.Time.now()
        msg.coordinate_frame = self._msg_cls.FRAME_LOCAL_NED
        msg.type_mask = (
            self._msg_cls.IGNORE_VX | self._msg_cls.IGNORE_VY | self._msg_cls.IGNORE_VZ
            | self._msg_cls.IGNORE_AFX | self._msg_cls.IGNORE_AFY | self._msg_cls.IGNORE_AFZ
            | self._msg_cls.IGNORE_YAW_RATE
        )  # = 2552 (0x9F8): 控位置 xyz + yaw
        msg.position = Point(x=nx, y=ny, z=nz)
        msg.yaw = yaw_ned
        self._setpoint_pub.publish(msg)

        # STREAMING 计数 (ARM 前置条件)
        with self._lock:
            if self._phase == "STREAMING":
                self._stream_count += 1
                self._px, self._py, self._pz = pos[0], pos[1], pos[2]
                self._yaw = yaw

        # offboard 丢失检测 (ACTIVE 时)
        self._check_offboard_lost()

    def publish_velocity(self, vel: list):
        """阶段2 位置控制为主, 速度 setpoint 暂不支持 (type_mask 位置模式)。"""
        logger.warning("[rosbridge] Phase2 publish_velocity not supported (position mode)")

    # ── offboard 状态机 ──
    def preflight(self, timeout: float = 90.0) -> bool:
        """推进 DISARMED → ACTIVE (阻塞, 供 lifecycle 启动前调用)。"""
        deadline = time.time() + timeout
        # 等 MAVROS 连接
        while time.time() < deadline:
            s = self._snapshot()
            if s["connected"]:
                break
            time.sleep(0.2)
        else:
            logger.error("[rosbridge] Phase2 preflight timeout: mavros not connected")
            return False
        logger.info("[rosbridge] Phase2 preflight: mavros connected")

        with self._lock:
            self._phase = "STREAMING"
            self._stream_count = 0
        logger.info("[rosbridge] Phase2 preflight: STREAMING (20Hz 位置 setpoint ≥3s)")

        # STREAMING 阶段: 由 GoalPublisher 持续 publish_position 推进计数;
        # preflight 自身也以 20Hz 发当前位置, 确保前置满足
        while time.time() < deadline:
            s = self._snapshot()
            with self._lock:
                pos = [self._px, self._py, self._pz]
                yaw = self._yaw
                count = self._stream_count
            self.publish_position(pos, yaw)
            if count >= 3 * 20:  # ≥3s @20Hz
                break
            time.sleep(0.05)
        else:
            logger.error("[rosbridge] Phase2 preflight timeout: stream not established")
            return False

        # ARM 前置: 距 home < 2m (design §7)
        dist_home = math.sqrt((self._px - self._home[0]) ** 2
                              + (self._py - self._home[1]) ** 2
                              + (self._pz - self._home[2]) ** 2)
        if dist_home > 2.0:
            logger.error(f"[rosbridge] Phase2 preflight refused: dist to home {dist_home:.1f}m > 2m")
            return False

        # ARM
        if not self._call_arm(True):
            logger.error("[rosbridge] Phase2 preflight failed: ARM rejected")
            return False
        with self._lock:
            self._phase = "OFFBOARD"
        # OFFBOARD
        if not self._call_mode("OFFBOARD"):
            logger.error("[rosbridge] Phase2 preflight failed: OFFBOARD rejected")
            self._call_arm(False)
            return False
        with self._lock:
            self._phase = "ACTIVE"
        logger.info("[rosbridge] Phase2 preflight: ACTIVE (offboard engaged)")
        return True

    def emergency_land(self):
        """应急降落: set_mode AUTO.LAND (design §5.3, abort/land 兜底)。"""
        with self._lock:
            if self._emergency:
                return
            self._emergency = True
        logger.warning("[rosbridge] Phase2 emergency_land: AUTO.LAND")
        try:
            self._call_mode("AUTO.LAND")
        except Exception as e:
            logger.error(f"[rosbridge] emergency_land failed: {e}")

    def _check_offboard_lost(self):
        """ACTIVE 下 mode 被切走 → 重切一次, 失败应急降落 (design §5.4)。"""
        s = self._snapshot()
        if s["phase"] != "ACTIVE" or s["mode"] == "OFFBOARD":
            return
        now = time.time()
        with self._lock:
            if self._offboard_lost_at is None:
                self._offboard_lost_at = now
            lost_for = now - self._offboard_lost_at
        if lost_for < 1.0:
            return  # 容忍瞬时
        logger.warning(f"[rosbridge] offboard lost (mode={s['mode']}), re-engaging...")
        if self._call_mode("OFFBOARD"):
            with self._lock:
                self._offboard_lost_at = None
            logger.info("[rosbridge] offboard re-engaged")
        else:
            self.emergency_land()

    # ── 服务调用 ──
    def _call_arm(self, value: bool) -> bool:
        try:
            if self._arm_proxy is None:
                rospy.wait_for_service("/mavros/cmd/arming", timeout=5.0)
                self._arm_proxy = rospy.ServiceProxy("/mavros/cmd/arming", self._arm_srv)
            resp = self._arm_proxy(value=value)
            return bool(resp.success)
        except Exception as e:
            logger.error(f"[rosbridge] arm({value}) failed: {e}")
            return False

    def _call_mode(self, custom_mode: str) -> bool:
        try:
            if self._mode_proxy is None:
                rospy.wait_for_service("/mavros/set_mode", timeout=5.0)
                self._mode_proxy = rospy.ServiceProxy("/mavros/set_mode", self._set_mode_srv)
            resp = self._mode_proxy(custom_mode=custom_mode)
            return bool(resp.mode_sent)
        except Exception as e:
            logger.error(f"[rosbridge] set_mode({custom_mode}) failed: {e}")
            return False


def make_adapter(phase: int = None) -> SetpointAdapter:
    """按 PHASE 环境变量 (默认 1) 创建适配器 (design §6)。"""
    if phase is None:
        phase = int(os.environ.get("PHASE", "1"))
    if phase == 1:
        return Phase1Adapter()
    if phase == 2:
        return Phase2Adapter()
    raise ValueError(f"Unknown PHASE={phase} (supported: 1, 2)")
