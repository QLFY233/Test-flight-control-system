"""
monitor 组件入口 — 10Hz 检测循环, 聚合 alert 上行。
每个检测周期跑所有检测器, 节流同 code 2s 一次, critical 不节流。
"""
from __future__ import annotations
import time
import threading
import logging
from .detector import DETECTORS, get_all
from bus.protocol import EVENT_TOOL_ALERT, SCHEMA_VERSION, TO_BETA

logger = logging.getLogger(__name__)


class MonitorComponent:
    """monitor 总线组件 — 持续产出 alert 事件。

    不接受 call, 只产 event:alert。
    """

    def __init__(self, state, rate: float = 10.0):
        self._state = state
        self._rate = rate
        self._period = 1.0 / rate
        self._running = False
        self._thread: threading.Thread | None = None
        # 事件发送回调
        self._send_event = None
        # 节流: code → 上次上告时间
        self._throttle: dict[str, float] = {}
        self._throttle_interval = 2.0  # 同 code 2s 内只上告一次
        # 运动加速度 (速度导数) 差分状态 — PX4 适配 (2026-08-03):
        # mavros imu/data 的 linear_acceleration 是含重力的传感器原始值 (≈9.81),
        # 直接检测会 overaccel 常亮误报。与 sim-drone 语义一致改为运动加速度
        # = 速度导数 (悬停/匀速 = 0, 加速/机动 = 真实加速度)。
        self._prev_vel: list | None = None
        self._prev_vel_ts: float = 0.0
        self._accel_smooth: list | None = None

    def set_event_sender(self, sender):
        self._send_event = sender

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="monitor", daemon=True)
        self._thread.start()
        logger.info(f"[monitor] started at {self._rate}Hz, {len(DETECTORS)} detector(s)")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        logger.info("[monitor] stopped")

    def handle(self, tool: str, args: dict) -> dict:
        return {"status": "ok", "note": "monitor does not accept calls"}

    def _loop(self):
        """10Hz 检测主循环。"""
        while self._running:
            try:
                self._tick()
            except Exception as e:
                logger.error(f"[monitor] tick error: {e}")
            time.sleep(self._period)

    def _motion_accel(self, vel: list) -> list:
        """运动加速度 = 速度导数 (一阶差分 + 帧级死区 + 低通平滑)。

        PX4 适配 (2026-08-03): mavros IMU linear_acceleration 含重力 (≈9.81 m/s²),
        monitor 的 overaccel 检测应使用运动加速度 (悬停/匀速 = 0) — 与 sim-drone
        (fake_drone_node.py 同款语义) 对齐, 消除含重力误报。
        首帧返回 0; 全轴速度变化 < 0.05 m/s (悬停/匀速) 清零; 低通 alpha=0.5。
        """
        now = time.time()
        if self._prev_vel is None or now <= self._prev_vel_ts:
            self._prev_vel = list(vel)
            self._prev_vel_ts = now
            return [0.0, 0.0, 0.0]
        dt = now - self._prev_vel_ts
        if dt <= 0:
            return [0.0, 0.0, 0.0]
        # 帧级死区: 全部轴速度变化 < 0.05 m/s 视为静止/匀速 (SITL 悬停噪声
        # ±0.03 m/s, tick 0.1s) — 直接清零且不残留平滑历史, 悬停/匀速恒 0
        if all(abs(v - v0) < 0.05 for v, v0 in zip(vel, self._prev_vel)):
            self._prev_vel = list(vel)
            self._prev_vel_ts = now
            self._accel_smooth = [0.0, 0.0, 0.0]
            return [0.0, 0.0, 0.0]
        acc = [(v - v0) / dt for v, v0 in zip(vel, self._prev_vel)]
        self._prev_vel = list(vel)
        self._prev_vel_ts = now
        if self._accel_smooth is None:
            self._accel_smooth = acc
        else:
            self._accel_smooth = [0.5 * a + 0.5 * s for a, s in zip(acc, self._accel_smooth)]
        return self._accel_smooth

    def _tick(self):
        """单次 tick: 构建 sample → 跑所有检测器 → 聚合 alert → 上行。"""
        # 构建遥测样本
        try:
            p = self._state.current_pose
            sample = {
                "pos": p.pos[:],
                "vel": p.vel[:],
                # PX4 适配: 运动加速度 = 速度导数 (IMU 原始值含重力, 见 _motion_accel)
                "accel": self._motion_accel(p.vel[:]),
                "angular_vel": p.angular_vel[:],
                "ts": time.time(),
                "last_data_ts": self._state.last_data_ts,
                "current_action_index": self._state.current_action_index,
                # B-5: 首帧前不评估 (启动时 vel/accel 恒零、z=0, 会刷假阳性)
                "data_received": self._state.data_received,
            }
        except Exception:
            return

        # 跑所有检测器
        all_alerts = []
        for detector in get_all():
            try:
                results = detector.update(sample)
                all_alerts.extend(results)
            except Exception as e:
                logger.warning(f"[monitor] detector '{detector.name}' error: {e}")

        # 节流 + 上行
        for alert in all_alerts:
            code = alert.get("code", "unknown")
            level = alert.get("level", "warning")
            now = alert.get("ts", time.time())

            # critical 不节流
            if level != "critical":
                last = self._throttle.get(code, 0)
                if now - last < self._throttle_interval:
                    continue

            self._throttle[code] = now
            self._send_alert(alert)

    def _send_alert(self, alert: dict):
        """上行 alert event。

        注意: to 保持 "beta" — 接口冻结 §3 表格明确 alert → "beta" (作 β 对话流系统消息),
        非笔误, 与 run_b/lifecycle 的 pose/telemetry→alpha 是两套路由。
        """
        if self._send_event:
            self._send_event({
                "schema_version": SCHEMA_VERSION,
                "from": "monitor",
                "to": TO_BETA,
                "msg_type": "event",
                "call_id": "",
                "tool": EVENT_TOOL_ALERT,
                "args": {},
                "payload": {
                    "level": alert.get("level", "warning"),
                    "code": alert.get("code", "unknown"),
                    "detail": alert.get("detail", ""),
                    "suggestion": None,  # B 侧不给建议, β 给
                    "ts": alert.get("ts", time.time()),
                    "action_index": alert.get("action_index"),
                },
                "ts": time.time(),
            })
