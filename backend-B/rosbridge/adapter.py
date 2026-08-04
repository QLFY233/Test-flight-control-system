"""
ROS 消息适配器 — 阶段抽象 (Phase1/Phase2)。
只改配置/前缀, 不动 small_model 上层 (PX4-阶段2-design.md §5)。

Phase1: sim-drone 假无人机 (/drone 前缀, PoseStamped setpoint)
Phase2: PX4 SITL + MAVROS (/mavros 前缀, PositionTarget + offboard 状态机)

坐标系: BState/A/前端/field.yaml 保持 ENU (x东 y北 z上);
NED↔ENU 变换单点收敛于本模块 (design §4.3)。

⚠️ 实测修正 (2026-08-03, S8.3b): MAVROS 上行话题 (local_position/pose、
velocity_local、imu/data) 本身已是 ROS ENU/FLU 约定 (REP-103), subscriber
恒等接入; 仅下行 /mavros/setpoint_raw/local 为裸传 mavlink (FRAME_LOCAL_NED),
须由本模块 enu_to_ned 变换。ned_to_enu 系列保留给未来裸 NED 数据源。
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
from bus.protocol import (
    SCHEMA_VERSION,
    EVENT_TOOL_ALERT,
    TO_BETA,
    ALERT_LEVEL_WARNING,
    ALERT_LEVEL_CRITICAL,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════
# NED ↔ ENU 变换 (单点收敛, PX4-阶段2-design.md §4.3)
# NED: x北 y东 z下 ; ENU: x东 y北 z上
# 用途: enu_to_ned/enu_yaw_to_ned = 下行 setpoint 现役路径;
#       ned_to_enu/ned_yaw_to_enu/ned_quat_to_enu_quat = 留给裸 NED 源
#       (MAVROS 上行已 ENU, 勿对 mavros 话题使用 — 会双重变换, 见 S8.3b)
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

    def __init__(self, prefix: str = PHASE2_PREFIX, home: list = None, state=None):
        from mavros_msgs.msg import PositionTarget, State
        from mavros_msgs.srv import CommandBool, SetMode

        self._msg_cls = PositionTarget
        self._state_cls = State
        self._arm_srv = CommandBool
        self._set_mode_srv = SetMode
        # BState 引用 (可选): preflight STREAMING 阶段发当前位置用 (subscriber 更新)
        self._state = state

        topics = get_phase2_topics(prefix)
        self._setpoint_pub = rospy.Publisher(
            topics["setpoint_raw"], PositionTarget, queue_size=10
        )
        # 虚拟 RC (mavlink override) — SITL 无真遥控, commander 的 ARM 检查要求
        # manual control 有效 ("Arming denied! manual control lost"); COM_RC_IN_MODE=1
        # 匹配 SOURCE_MAVLINK, 由本线程持续发中性 RC 提供有效输入 (design §7.6)
        from mavros_msgs.msg import OverrideRCIn
        self._rc_pub = rospy.Publisher(
            "/mavros/rc/override", OverrideRCIn, queue_size=10
        )
        self._rc_running = False
        self._rc_thread = None
        self._home = list(home) if home else [0.0, 0.0, 0.5]
        self._lock = threading.Lock()
        self._phase = "DISARMED"          # 状态机当前阶段
        self._mav_connected = False
        self._mav_armed = False
        self._mav_mode = ""
        self._stream_count = 0            # STREAMING 已发帧数
        self._offboard_lost_at = None     # 非主动切出 OFFBOARD 的时刻
        self._offboard_retries = 0        # offboard 重切连续失败次数 (S8.6: 2 次后应急降落)
        self._emergency = False           # 已触发应急降落
        self._setpoint_z = 0.0            # 最近一次下发 setpoint 的 z (重新起飞判定用)
        self._rearm_cooldown = 0.0        # 重新武装冷却 (防 20Hz 反复触发)
        self._send_event = None           # alert 事件上行回调 (dispatch.send_event)

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

    def _snapshot(self):
        with self._lock:
            return dict(
                connected=self._mav_connected, armed=self._mav_armed,
                mode=self._mav_mode, phase=self._phase,
                offboard_lost_at=self._offboard_lost_at,
            )

    # ── alert 上行 (design §5.4/§7, S8.6/S8.8) ──
    def set_event_sender(self, sender):
        """注入 alert 事件上行回调 (fn: dict → None, 即 dispatch.send_event)。

        IPC 未连接时 send_event 可能抛异常 — _send_alert 内部 try/except 容错。
        """
        self._send_event = sender

    def _send_alert(self, level: str, code: str, detail: str = ""):
        """上行 alert event — 帧格式与 monitor._send_alert 一致 (design §5.4)。

        to 保持 "beta" — 接口冻结 §3 表格 alert → "beta" (作 β 对话流系统消息)。
        """
        if self._send_event is None:
            logger.warning(f"[rosbridge] alert({code}) not sent — no event sender wired")
            return
        try:
            self._send_event({
                "schema_version": SCHEMA_VERSION,
                "from": "B",
                "to": TO_BETA,
                "msg_type": "event",
                "call_id": "",
                "tool": EVENT_TOOL_ALERT,
                "args": {},
                "payload": {
                    "level": level,
                    "code": code,
                    "detail": detail,
                    "suggestion": None,  # B 侧不给建议, β 给
                    "ts": time.time(),
                    "action_index": None,
                },
                "ts": time.time(),
            })
        except Exception as e:
            logger.error(f"[rosbridge] alert({code}) send failed: {e}")

    # ── setpoint 下发 ──
    def publish_position(self, pos: list, yaw: float):
        """下发位置 setpoint (入参 ENU, 直接透传)。

        ⚠️ 2026-08-03 实测修正 (S8.3b 根因): mavros 1.20.1 的 setpoint_raw
        local_cb 对非 body 帧执行 ENU→NED 变换 (含 yaw), B 侧若再变换 =
        双重变换, FCU 收到 ENU 值当 NED — takeoff z=+1.0(向下) → PX4
        want_takeoff 永不成立 → 起飞状态机卡死 (爬升受限)。故此处原样透传。
        """
        msg = self._msg_cls()
        msg.header.stamp = rospy.Time.now()
        msg.coordinate_frame = self._msg_cls.FRAME_LOCAL_NED
        msg.type_mask = (
            self._msg_cls.IGNORE_VX | self._msg_cls.IGNORE_VY | self._msg_cls.IGNORE_VZ
            | self._msg_cls.IGNORE_AFX | self._msg_cls.IGNORE_AFY | self._msg_cls.IGNORE_AFZ
            | self._msg_cls.IGNORE_YAW_RATE
        )  # = 2552 (0x9F8): 控位置 xyz + yaw
        msg.position = Point(x=pos[0], y=pos[1], z=pos[2])
        msg.yaw = yaw
        self._setpoint_pub.publish(msg)
        self._setpoint_z = pos[2]

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
    def _ensure_spin(self):
        """确保 rospy 回调分发线程在跑 (preflight 可能先于调用方 spin 执行)。

        rospy 无 spin_once; 回调必须由 spin 线程分发。
        preflight 的等待循环依赖 /mavros/state 回调更新状态。
        """
        if getattr(rospy, "_spin_thread", None) is None:
            t = threading.Thread(target=rospy.spin, name="rospy-spin", daemon=True)
            t.start()
            logger.info("[rosbridge] Phase2 rospy spin thread started")

    def _start_streaming(self):
        """启动 setpoint 流线程 (20Hz 发当前位置)。

        PX4 offboard 需要持续 setpoint 流 (停发 ≥1s 自动退出 offboard),
        且切换 OFFBOARD 前后都不能断流 — 故 STREAMING→OFFBOARD→ARM→ACTIVE
        全程由本线程维持, ACTIVE 后由 GoalPublisher 接管。
        """
        self._streaming = True
        self._stream_thread = threading.Thread(target=self._stream_loop, name="phase2-stream", daemon=True)
        self._stream_thread.start()

    def _stop_streaming(self):
        self._streaming = False
        if self._stream_thread is not None:
            self._stream_thread.join(timeout=1.0)
            self._stream_thread = None

    def _stream_loop(self):
        while self._streaming and not rospy.is_shutdown():
            try:
                pos, yaw = self._current_pos_yaw()
                self.publish_position(pos, yaw)
            except Exception as e:
                logger.error(f"[rosbridge] stream loop error: {e}")
            time.sleep(0.05)  # 20Hz

    def _current_pos_yaw(self):
        """取 BState 当前位姿 (ENU), 无 state 时用内部缓存。"""
        if self._state is not None:
            try:
                from small_model.component import yaw_from_quat
                p = self._state.current_pose
                return p.pos[:], yaw_from_quat(p.quat[:])
            except Exception:
                pass
        return [self._px, self._py, self._pz], self._yaw

    def _start_virtual_rc(self):
        """启动虚拟 RC 线程: 持续发中性 RC override (2Hz) 满足 ARM 检查。

        SITL 无真遥控, PX4 commander 的 preArm 检查需要 valid manual control;
        经 mavros /rc/override 发 SOURCE_MAVLINK 数据 (COM_RC_IN_MODE=1 匹配)。
        """
        if self._rc_thread is not None:
            return
        self._rc_running = True
        self._rc_thread = threading.Thread(target=self._rc_loop, name="virtual-rc", daemon=True)
        self._rc_thread.start()
        logger.info("[rosbridge] Phase2 virtual RC started (neutral override)")

    def _stop_virtual_rc(self):
        self._rc_running = False
        if self._rc_thread is not None:
            self._rc_thread.join(timeout=1.0)
            self._rc_thread = None

    def _rc_loop(self):
        from mavros_msgs.msg import OverrideRCIn
        # 通道 (共 18):
        #   ch1-3 roll/pitch/yaw 中性 1500; ch4 油门最低 1000 (安全低油门);
        #   ch5/ch6 mode/arm switch 中性 1500 (0 会被解析为开关位置触发 RTL!); 其余 0
        # rc_update 只在通道值变化时发布 manual_control_setpoint (rc_update.cpp:
        # "limit processing if there's no update") — 固定值永远不会触发更新,
        # commander 将一直报 rc_signal_lost。故每个 tick 微抖 (±1 PWM ≈ 0.1%)。
        tick = 0
        while self._rc_running and not rospy.is_shutdown():
            tick += 1
            d = 1 if (tick % 2) else -1
            msg = OverrideRCIn()
            msg.channels = [1500 + d, 1500, 1500, 1000 + (1 if d > 0 else 0),
                            1500, 1500, 0, 0] + [0] * 10
            try:
                self._rc_pub.publish(msg)
            except Exception as e:
                logger.error(f"[rosbridge] virtual RC publish failed: {e}")
            time.sleep(0.2)

    def preflight(self, timeout: float = 90.0) -> bool:
        """推进 DISARMED → ACTIVE (阻塞, 供 lifecycle 启动前调用)。"""
        self._ensure_spin()
        self._start_virtual_rc()
        deadline = time.time() + timeout
        # 等 MAVROS 连接
        while time.time() < deadline:
            s = self._snapshot()
            if s["connected"]:
                break
            time.sleep(0.05)
        else:
            logger.error("[rosbridge] Phase2 preflight timeout: mavros not connected")
            self._send_alert(ALERT_LEVEL_WARNING, "preflight_refused",
                             "mavros not connected within timeout")
            return False
        logger.info("[rosbridge] Phase2 preflight: mavros connected")

        # 等首帧真实位姿 (subscriber → BState) 再发 setpoint — 否则 STREAMING
        # 首帧发合成默认位姿 [0,0,0], 与真实地面位置的偏差会被 PX4 执行为
        # 非预期小跳 (2026-08-03 实测: 启动即 "Takeoff detected" 漂移)
        if self._state is not None:
            while time.time() < deadline:
                try:
                    if getattr(self._state, "_data_received", False):
                        break
                except Exception:
                    pass
                time.sleep(0.1)
            else:
                logger.error("[rosbridge] Phase2 preflight timeout: no pose from subscriber")
                self._send_alert(ALERT_LEVEL_WARNING, "preflight_refused",
                                 "no pose from subscriber within timeout")
                return False
            logger.info("[rosbridge] Phase2 preflight: first real pose received")

        with self._lock:
            self._phase = "STREAMING"
            self._stream_count = 0
        # setpoint 流线程: 贯穿 STREAMING→OFFBOARD→ARM 全程 (offboard 断流即退出)
        self._start_streaming()
        logger.info("[rosbridge] Phase2 preflight: STREAMING (20Hz 位置 setpoint ≥3s)")

        # STREAMING ≥3s (流线程维持 setpoint, 此处仅计时)
        time.sleep(3.0)

        # ARM 前置: 距 home < 2m (design §7)
        pos, _y = self._current_pos_yaw()
        dist_home = math.sqrt((pos[0] - self._home[0]) ** 2
                              + (pos[1] - self._home[1]) ** 2
                              + (pos[2] - self._home[2]) ** 2)
        if dist_home > 2.0:
            logger.error(f"[rosbridge] Phase2 preflight refused: dist to home {dist_home:.1f}m > 2m")
            self._send_alert(ALERT_LEVEL_WARNING, "preflight_refused",
                             f"dist to home {dist_home:.1f}m > 2m (ARM pre-check)")
            self._stop_streaming()
            return False

        # OFFBOARD→ARM 重试环: PX4 在 EKF/GPS home 未就绪时拒切 OFFBOARD
        # (2026-08-03 实测: B 启动过快撞上 EKF 预热窗口 → OFFBOARD rejected)。
        # 对齐 design §5.4 "PX4 拒 ARM → 停在 STREAMING 重试", 流线程全程维持。
        attempt = 0
        while time.time() < deadline:
            attempt += 1
            # 切 OFFBOARD (先于 ARM — 官方 offboard 例程顺序: OFFBOARD 模式的
            # flag_control_manual_enabled=false, preArm 的 manual control 检查被跳过,
            # 避免无 RC 环境 "Arming denied! manual control lost")
            # 若当前是自动模式 (AUTO.*) 且直切失败, 先 POSCTL 再重试
            if not self._call_mode("OFFBOARD") or not self._wait_mode("OFFBOARD", timeout=3.0):
                logger.warning("[rosbridge] Phase2 preflight: direct OFFBOARD failed, via POSCTL")
                if self._call_mode("POSCTL"):
                    time.sleep(0.3)
                    if not self._call_mode("OFFBOARD") or not self._wait_mode("OFFBOARD", timeout=3.0):
                        logger.warning(f"[rosbridge] Phase2 preflight attempt {attempt}: OFFBOARD rejected, retry")
                        time.sleep(2.0)
                        continue
                else:
                    logger.warning(f"[rosbridge] Phase2 preflight attempt {attempt}: cannot switch POSCTL, retry")
                    time.sleep(2.0)
                    continue
            with self._lock:
                self._phase = "OFFBOARD"

            # ARM (OFFBOARD 模式下 manual control 检查不生效; 流线程持续发 setpoint)
            if not self._call_arm(True):
                logger.warning(f"[rosbridge] Phase2 preflight attempt {attempt}: ARM rejected, retry")
                time.sleep(2.0)
                continue
            # 验证 armed
            if not self._wait_armed(timeout=3.0):
                logger.warning(f"[rosbridge] Phase2 preflight attempt {attempt}: not armed after ARM, retry")
                self._call_arm(False)
                time.sleep(2.0)
                continue
            # 起飞边沿: 已武装但落地静止时, PX4 landed 钳制锁死位置控制
            # (takeoff 状态机需要 disarm→arm 边沿才触发) — 实测 2026-08-03:
            # 地面已武装无人机对爬升 setpoint 完全无响应。静止判定见
            # _is_grounded_still (2s 速度 < 0.15m/s)。
            if self._is_grounded_still():
                logger.warning("[rosbridge] Phase2 preflight: grounded & armed — disarm/re-arm for takeoff edge")
                self._call_arm(False)
                time.sleep(1.5)
                if not self._call_arm(True) or not self._wait_armed(timeout=3.0):
                    logger.warning(f"[rosbridge] Phase2 preflight attempt {attempt}: re-arm after disarm failed, retry")
                    time.sleep(2.0)
                    continue
            with self._lock:
                self._phase = "ACTIVE"
            # ACTIVE: 停流线程, 由 GoalPublisher 接管 (20Hz 持续)
            self._stop_streaming()
            logger.info(f"[rosbridge] Phase2 preflight: ACTIVE (offboard engaged, armed, attempt {attempt})")
            return True
        logger.error("[rosbridge] Phase2 preflight failed: OFFBOARD/ARM retry exhausted")
        self._send_alert(ALERT_LEVEL_WARNING, "preflight_refused",
                         "OFFBOARD/ARM retry exhausted")
        self._stop_streaming()
        return False

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

    def _is_grounded_still(self) -> bool:
        """判断无人机是否已落地静止 (armed 且速度持续接近 0)。

        PX4 landed 钳制: 落地后位置控制被锁, 必须 disarm→arm 触发 takeoff
        状态机才能重新起飞 (2026-08-03 实测)。用 BState 速度 (mavros ENU)
        连续采样 2s: 均 < 0.15m/s 视为静止。空中悬停 |v|≈0 也会命中 — 但
        preflight 在 ACTIVE 前评估, 空中漂移悬停通常 |v|>0.15 不命中;
        落地静止必命中 (v≈0)。
        """
        if self._state is None:
            return False
        try:
            speeds = []
            t0 = time.time()
            while time.time() - t0 < 2.0:
                with self._state.pose_lock:
                    v = self._state._pose.vel
                    speeds.append((v[0] ** 2 + v[1] ** 2 + v[2] ** 2) ** 0.5)
                time.sleep(0.2)
            return all(s < 0.15 for s in speeds) and len(speeds) >= 5
        except Exception:
            return False

    def _check_offboard_lost(self):
        """ACTIVE 下 mode 被切走 → 重切 OFFBOARD; 连续失败 2 次 → 应急降落 (design §5.4)。

        S8.6 时序: 容忍瞬时 (<1s) → 重切 OFFBOARD (mode_sent + mode 确认);
        失败 → alert(critical, offboard_lost) + 计数; 连续失败 2 次 → emergency_land()
        (AUTO.LAND)。应急降落进行中 (_emergency) 不得被 offboard-lost 重切覆盖 (S8.5)。

        2026-08-04 补充 (落地后重新起飞): 飞行计划以 land 结束 → AUTO.LAND → disarm,
        _emergency 恒 True 会永久阻塞重新武装。现改为: 无人机已落地解锁 (armed=False) 即
        视为安全, 清除 emergency 状态; 若当前目标 z 高于地面 (起飞类), 重切 OFFBOARD 同时
        重新 ARM (冷却 5s 防 20Hz 反复触发)。
        """
        s = self._snapshot()
        if s["phase"] != "ACTIVE":
            return
        if s["mode"] == "OFFBOARD":
            # mode 已恢复 — 复位丢失计时/重试计数 (防旧状态污染下次检测)
            with self._lock:
                self._offboard_lost_at = None
                self._offboard_retries = 0
            # 落地解锁 + 当前 setpoint 是起飞目标 (z 高于地面) → 重新武装
            self._maybe_rearm_if_needed(now=time.time())
            return
        with self._lock:
            if self._emergency and not s["armed"] and self._is_grounded():
                # 应急降落已完成 (已落地解锁) — 允许重新起飞, 清除 emergency
                logger.info("[rosbridge] landed & disarmed — clearing emergency, allow re-engage")
                self._emergency = False
            elif self._emergency:
                # S8.5: 应急降落进行中 (仍在空中/仍武装) — 不得被覆盖;
                # 空中解锁不视为落地 (防 emergency 标志被空中 disarm 误清后重切 OFFBOARD)
                return
        now = time.time()
        with self._lock:
            if self._offboard_lost_at is None:
                self._offboard_lost_at = now
            lost_for = now - self._offboard_lost_at
        if lost_for < 1.0:
            return  # 容忍瞬时 (mode 切换抖动)
        logger.warning(f"[rosbridge] offboard lost (mode={s['mode']}), re-engaging...")
        if self._call_mode("OFFBOARD") and self._wait_mode("OFFBOARD", timeout=3.0):
            self._maybe_rearm_if_needed(now=now)
            with self._lock:
                self._offboard_lost_at = None
                self._offboard_retries = 0
            logger.info("[rosbridge] offboard re-engaged")
            return
        # 重切失败: alert + 计数, 连续 2 次 → 应急降落
        with self._lock:
            self._offboard_retries += 1
            retries = self._offboard_retries
        self._send_alert(ALERT_LEVEL_CRITICAL, "offboard_lost",
                         f"offboard lost (mode={s['mode']}), re-engage failed {retries}/2")
        if retries >= 2:
            logger.error("[rosbridge] offboard lost: 2 consecutive re-engage failures — emergency land")
            self.emergency_land()

    def _maybe_rearm_if_needed(self, now):
        """落地解锁 + 当前 setpoint 为起飞目标 → 重新武装 (冷却 5s)。

        触发时机: 每次 publish_position 检测 (ACTIVE 且 mode=OFFBOARD) 时调用,
        覆盖"落地后重新连上 OFFBOARD, 但 takeoff 目标稍后才到达"的窗口 (2026-08-04)。

        判定: 目标 z ≥ home 高度 (起飞目标) + 无人机实际在地面附近, 防空中误触发。
        """
        if self._mav_armed:
            return
        # 目标 z 明显高于 home → 是起飞目标 (降落 hold point 在地面, z 低, 不满足)
        if self._setpoint_z < self._home[2]:
            return
        # 无人机需确实在地面附近 (防空中 disarm 误触发)
        if not self._is_grounded():
            return
        rearm = False
        with self._lock:
            if now - self._rearm_cooldown >= 5.0:
                self._rearm_cooldown = now
                rearm = True
        if rearm:
            self._rearm_after_land()

    def _is_grounded(self):
        """判断无人机实际位置在地面附近 (ENU z < home 高度 - 0.3)。"""
        try:
            cur_z = self._current_pos_yaw()[0][2]
        except Exception:
            return False
        return cur_z <= self._home[2] - 0.3

    def _rearm_after_land(self):
        """落地解锁后重新武装 (起飞边沿: 先 disarm→arm, 触发 PX4 takeoff 状态机)。

        preflight 中同样的"已武装但落地静止"处理 (S8 实测: 地面已武装无人机对
        爬升 setpoint 无响应, 需 disarm→arm 边沿)。在后台线程执行, 避免阻塞
        goal-publisher 的 20Hz setpoint 流 (OFFBOARD 停发可能退出)。
        """
        def worker():
            logger.info("[rosbridge] re-arm after land (disarm→arm takeoff edge)")
            try:
                if self._mav_armed:
                    self._call_arm(False)
                    time.sleep(1.5)
                if self._call_arm(True) and self._wait_armed(timeout=3.0):
                    logger.info("[rosbridge] re-armed for takeoff")
                else:
                    logger.warning("[rosbridge] re-arm failed")
            except Exception as e:
                logger.error(f"[rosbridge] re-arm error: {e}")

        threading.Thread(target=worker, name="rearm-after-land", daemon=True).start()

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

    def _wait_mode(self, custom_mode: str, timeout: float = 3.0) -> bool:
        """轮询 /mavros/state 确认模式实际切换 (mode_sent 只是命令已发出)。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            s = self._snapshot()
            if s["mode"] == custom_mode:
                return True
            time.sleep(0.1)
        return False

    def _wait_armed(self, timeout: float = 3.0) -> bool:
        """轮询 /mavros/state 确认已武装。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            s = self._snapshot()
            if s["armed"]:
                return True
            time.sleep(0.1)
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


def make_adapter(phase: int = None, state=None) -> SetpointAdapter:
    """按 PHASE 环境变量 (默认 1) 创建适配器 (design §6)。"""
    if phase is None:
        phase = int(os.environ.get("PHASE", "1"))
    if phase == 1:
        return Phase1Adapter()
    if phase == 2:
        return Phase2Adapter(state=state)
    raise ValueError(f"Unknown PHASE={phase} (supported: 1, 2)")
