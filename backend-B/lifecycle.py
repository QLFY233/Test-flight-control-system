"""
后端 B 生命周期 — 启动 N 步 + 关停序列。
线程模型: rospy 主 + 目标点(20Hz) + uplink(10Hz) + IPC recv。
"""
from __future__ import annotations
import sys
import time
import signal
import logging
import threading

from config_loader import load_field, load_constraints
from state import BState
from bus import registry as bus_registry
from bus.router import call as bus_call
from bus.protocol import SCHEMA_VERSION, TO_SMALL_MODEL

logger = logging.getLogger(__name__)

_keep_running = True
_last_warn: dict[str, float] = {}


def _warn_rate_limited(logger_obj, message: str, period: float = 5.0):
    """Rate-limited warning — suppresses repeats within `period` seconds."""
    now = time.time()
    last = _last_warn.get(message, 0.0)
    if now - last >= period:
        _last_warn[message] = now
        logger_obj.warning(f"{message} (suppressed for {period}s)")


def _signal_handler(sig, frame):
    global _keep_running
    logger.info(f"[lifecycle] received signal {sig}, shutting down...")
    _keep_running = False


class Lifecycle:
    """后端 B 的启动/运行/关停。"""

    def __init__(self, config_dir: str = "config"):
        self.config_dir = config_dir
        self.state: BState | None = None
        self.ipc_client = None
        self.dispatch = None
        self._small_model_component = None
        self._subscriber = None
        self._goal_publisher = None
        self._threads: list[threading.Thread] = []

    def run(self):
        """主入口 — 启动并阻塞直到关停。"""
        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)

        logger.info("[lifecycle] === Backend-B starting (stage F) ===")

        # 1. Load config
        field = load_field(f"{self.config_dir}/field.yaml")
        constraints = load_constraints(f"{self.config_dir}/default_constraints.yaml")
        logger.info("[lifecycle] config loaded")

        # 2. Create state
        self.state = BState(field, constraints)

        # 3. Init ROS node
        self._init_ros()

        # 4. Init B bus registry (real small_model)
        self._init_bus()

        # 5. Init IPC client
        from ipc.client import IpcClient
        from ipc.dispatch import Dispatch
        self.ipc_client = IpcClient(self.state)
        self.dispatch = Dispatch(self.state, self.ipc_client)
        self.ipc_client.set_frame_handler(self.dispatch.handle_incoming)

        # Wire small_model event sender → dispatch.send_event
        self._small_model_component.set_event_sender(self.dispatch.send_event)
        # Wire monitor event sender → dispatch.send_event
        self._monitor_component.set_event_sender(self.dispatch.send_event)
        # 契约 §6: 断连 → small_model 切 hover (与 run_b.py 路径一致)
        self.ipc_client.set_disconnect_handler(self._on_ipc_disconnect)

        # 6. Init ROS subscriber
        self._subscriber = self._init_subscriber()

        # 7. Connect to A
        if not self.ipc_client.connect():
            logger.warning("[lifecycle] initial connect to A failed, will retry in recv loop")

        # 8. Start threads (IPC recv + uplink + goal publisher)
        self._start_threads()

        # 9. Main loop — rospy spin (subscriber callbacks)
        logger.info("[lifecycle] Backend-B running, Ctrl+C to stop")
        try:
            import rospy
            while _keep_running and not rospy.is_shutdown():
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass

        # 10. Shutdown
        self._shutdown()
        logger.info("[lifecycle] Backend-B stopped")

    def _init_ros(self):
        """初始化 ROS 节点。"""
        try:
            import rospy
            rospy.init_node("backend_b", anonymous=False, disable_signals=True)
            logger.info("[lifecycle] ROS node 'backend_b' initialized")
        except Exception as e:
            logger.warning(f"[lifecycle] ROS init skipped: {e}")

    def _init_bus(self):
        """初始化 B 内总线, 注册真实的 small_model + monitor 组件。"""
        from small_model.component import SmallModelComponent
        from monitor.component import MonitorComponent
        from monitor.detector import DETECTORS, register as det_register
        from monitor.thresholds import ThresholdDetector
        from monitor.trends import TrendDetector

        self._small_model_component = SmallModelComponent(self.state)

        # 注册检测器
        det_register(ThresholdDetector(self.state.field, self.state.default_constraints))
        det_register(TrendDetector())
        logger.info(f"[lifecycle] {len(DETECTORS)} detector(s) registered")

        # 创建 monitor 组件
        self._monitor_component = MonitorComponent(self.state)

        bus_registry.init_registry(
            small_model_component=self._small_model_component,
            monitor_component=self._monitor_component,
        )
        logger.info("[lifecycle] bus registry initialized (small_model + monitor)")

    def _init_subscriber(self):
        """初始化 ROS 订阅器 (两阶段均恒等变换, design §6)。

        阶段2 不再注入 ned_to_enu: MAVROS 上行话题已是 ROS ENU/FLU
        (REP-103), 双重变换曾致爬升受限 (2026-08-03 ulog 实证, S8.3b)。
        NED→ENU 仅存在于下行 adapter (setpoint_raw 裸传, design §4.3)。
        """
        try:
            from rosbridge.subscriber import DroneSubscriber
            sub = DroneSubscriber(self.state)
            return sub
        except Exception as e:
            logger.warning(f"[lifecycle] ROS subscriber init failed (no ROS?): {e}")
            return None

    def _start_threads(self):
        """启动各工作线程。"""

        # IPC recv thread
        t_ipc = threading.Thread(
            target=self.ipc_client.recv_loop,
            name="ipc-recv",
            daemon=True,
        )
        t_ipc.start()
        self._threads.append(t_ipc)

        # Uplink thread (10Hz pose + telemetry)
        t_uplink = threading.Thread(
            target=self._uplink_loop,
            name="uplink",
            daemon=True,
        )
        t_uplink.start()
        self._threads.append(t_uplink)

        # Monitor thread (10Hz, 阶段 I)
        self._monitor_component.start()

        # Goal publisher thread (20Hz, 先连 A 再启)
        if self.state.ipc_connected:
            self._start_goal_publisher()
        else:
            # 延迟启动: 等 IPC 连上后再启
            t_goal_delayed = threading.Thread(
                target=self._delayed_goal_publisher_start,
                name="goal-delayed",
                daemon=True,
            )
            t_goal_delayed.start()
            self._threads.append(t_goal_delayed)

        logger.info("[lifecycle] threads started (ipc + uplink + goal)")

    def _start_goal_publisher(self):
        """启动目标点发布线程 (按 PHASE 选择 adapter; 阶段2 先 preflight)。"""
        if self._goal_publisher is not None:
            return
        try:
            from rosbridge.adapter import make_adapter
            from rosbridge.publisher import GoalPublisher
            adapter = make_adapter(state=self.state)
            # S8.5: abort → AUTO.LAND 兜底 (design §5.3, 比悬停更保守)
            if self.dispatch is not None:
                self.dispatch.set_abort_handler(adapter.emergency_land)
            # 阶段2: 等 offboard 就绪 (阻塞 ≤90s, 失败仅告警 — publisher 仍会持续发 setpoint)
            if not adapter.preflight(timeout=90.0):
                logger.warning("[lifecycle] phase2 preflight failed — goal publisher runs without offboard")
            self._goal_publisher = GoalPublisher(
                self.state, self._small_model_component, adapter, rate=20.0
            )
            self._goal_publisher.start()
        except Exception as e:
            logger.warning(f"[lifecycle] goal publisher init failed: {e}")

    def _delayed_goal_publisher_start(self):
        """等 IPC 连上后再启目标点线程。"""
        logger.info("[lifecycle] waiting for IPC connection before starting goal publisher...")
        while _keep_running and not self.state.ipc_connected:
            time.sleep(0.5)
        if _keep_running:
            self._start_goal_publisher()

    def _on_ipc_disconnect(self):
        """IPC 意外断连回调 — small_model 切 hover (契约 §6)。"""
        try:
            bus_call(to=TO_SMALL_MODEL, tool="hover", args={})
            logger.warning("[lifecycle] IPC disconnected — small_model switched to hover")
        except Exception as e:
            logger.warning(f"[lifecycle] disconnect hover failed: {e}")

    def _uplink_loop(self):
        """10Hz 上行线程: 读 BState → IPC 发 pose + telemetry。"""
        period = 0.1  # 10Hz
        while _keep_running:
            start = time.time()
            try:
                self._send_uplink_pose()
                self._send_uplink_telemetry()
            except Exception as e:
                logger.error(f"[uplink] error: {e}")
            elapsed = time.time() - start
            sleep_time = max(0, period - elapsed)
            time.sleep(sleep_time)

    def _send_uplink_pose(self):
        """上行 pose event (接口冻结 §5)。"""
        if not self.state.ipc_connected:
            return
        try:
            p = self.state.current_pose
            msg = {
                "schema_version": SCHEMA_VERSION,
                "from": "B",
                "to": "alpha",
                "msg_type": "event",
                "call_id": "",
                "tool": "pose",
                "args": {},
                "payload": {
                    "pos": p.pos[:],
                    "quat": p.quat[:],  # [w,x,y,z]
                    "vel": p.vel[:],
                    "accel": p.accel[:],
                    "angularVel": p.angular_vel[:],
                    # B-10: 统一 wall time (与 run_b.py 一致; ROS header stamp 不用于停产判定)
                    "ts": time.time(),
                },
                "ts": time.time(),
            }
            self.dispatch.send_event(msg)
        except Exception as e:
            _warn_rate_limited(logger, f"[uplink] pose send failed: {e}", period=5.0)

    def _send_uplink_telemetry(self):
        """上行 telemetry event (接口冻结 §5, 不入前端, 仅入库)。
        payload 按冻结 {vel, accel, imu, ts}; 保留 angularVel 冗余字段向后兼容。"""
        if not self.state.ipc_connected:
            return
        try:
            p = self.state.current_pose
            imu = self.state.current_imu
            msg = {
                "schema_version": SCHEMA_VERSION,
                "from": "B",
                "to": "alpha",
                "msg_type": "event",
                "call_id": "",
                "tool": "telemetry",
                "args": {},
                "payload": {
                    "vel": p.vel[:],
                    "accel": imu.accel[:],
                    "angularVel": imu.angular_vel[:],
                    "imu": {"accel": imu.accel[:], "angular_vel": imu.angular_vel[:], "ts": imu.ts},
                    "ts": time.time(),
                },
                "ts": time.time(),
            }
            self.dispatch.send_event(msg)
        except Exception as e:
            _warn_rate_limited(logger, f"[uplink] telemetry send failed: {e}", period=5.0)

    def _shutdown(self):
        """关停: hover → stop publisher → rospy shutdown → close socket。"""
        logger.info("[lifecycle] shutting down...")

        # 1. Hover
        try:
            bus_call(to="small_model", tool="hover", args={})
        except Exception as e:
            logger.warning(f"[lifecycle] hover on shutdown failed: {e}")

        # 2. Stop goal publisher
        if self._goal_publisher:
            self._goal_publisher.stop()

        # 2.5 Stop monitor
        self._monitor_component.stop()

        # 3. Shutdown subscriber
        if self._subscriber:
            try:
                self._subscriber.shutdown()
            except Exception as e:
                logger.warning(f"[lifecycle] subscriber shutdown error: {e}")

        # 4. ROS shutdown
        try:
            import rospy
            rospy.signal_shutdown("backend B shutdown")
        except Exception:
            pass

        # 5. Close IPC
        if self.ipc_client:
            self.ipc_client.close()

        # 6. Wait threads
        for t in self._threads:
            t.join(timeout=2.0)

        logger.info("[lifecycle] shutdown complete")
