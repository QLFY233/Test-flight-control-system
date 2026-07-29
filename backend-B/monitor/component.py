"""
monitor 组件入口 — 10Hz 检测循环, 聚合 alert 上行。
每个检测周期跑所有检测器, 节流同 code 2s 一次, critical 不节流。
"""
from __future__ import annotations
import time
import threading
import logging
from .detector import DETECTORS, get_all
from bus.protocol import EVENT_TOOL_ALERT

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

    def _tick(self):
        """单次 tick: 构建 sample → 跑所有检测器 → 聚合 alert → 上行。"""
        # 构建遥测样本
        try:
            p = self._state.current_pose
            sample = {
                "pos": p.pos[:],
                "vel": p.vel[:],
                "accel": p.accel[:],
                "angular_vel": p.angular_vel[:],
                "ts": time.time(),
                "last_data_ts": self._state.last_data_ts,
                "current_action_index": self._state.current_action_index,
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
        """上行 alert event。"""
        if self._send_event:
            self._send_event({
                "schema_version": 2,
                "from": "monitor",
                "to": "beta",
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
