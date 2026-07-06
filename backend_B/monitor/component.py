"""
Monitor component: runs all safety detectors on each cycle and
aggregates/throttles alerts before forwarding to Backend A via IPC.

Throttling rules:
  - Same alert code: 2-second cooldown between sends.
  - Critical severity: NEVER throttled (always sent immediately).
"""

import time
import logging
import threading
from typing import Any, Optional

from backend_B.monitor.detector import DETECTORS, get_detectors
from backend_B.monitor.thresholds import ThresholdDetector
from backend_B.monitor.trends import TrendDetector

logger = logging.getLogger("backend_b.monitor")

# Monitor tick rate
MONITOR_TICK_RATE = 10.0  # Hz
MONITOR_TICK_INTERVAL = 1.0 / MONITOR_TICK_RATE


class MonitorComponent:
    """
    Bus component that aggregates safety detectors and manages alert flow.

    Registered as "monitor" in the bus registry.
    """

    def __init__(self, default_constraints: dict, field_config=None):
        """
        Args:
            default_constraints: System default constraints.
            field_config: FieldConfig for boundary/obstacle data.
        """
        self._default_constraints = default_constraints
        self._field_config = field_config

        # Throttling state: code -> last sent timestamp
        self._throttle_state: dict = {}
        self._throttle_lock = threading.Lock()
        self._throttle_interval = 2.0  # seconds

        # Initialize detectors
        self._init_detectors()

    def _init_detectors(self) -> None:
        """Create and register built-in detectors."""
        from backend_B.monitor.detector import register_detector

        constraints = self._default_constraints

        # Threshold detector
        boundary_x = (0.0, 5.0)
        boundary_y = (0.0, 4.0)
        boundary_z = (0.0, 3.0)

        if self._field_config is not None:
            boundary_x = self._field_config.boundary.x
            boundary_y = self._field_config.boundary.y
            boundary_z = self._field_config.boundary.z

        thresh = ThresholdDetector(
            boundary_x=boundary_x,
            boundary_y=boundary_y,
            boundary_z=boundary_z,
            speed_max=constraints.get("speed_max", 1.5),
            accel_max=constraints.get("accel_max", 2.0),
            angular_velocity_max=constraints.get("angular_velocity_max", 0.5),
            ceiling=constraints.get("ceiling", 2.5),
            floor=constraints.get("floor", 0.3),
            data_stale_max_age=1.0,
            tracking_error_max=1.0,
        )
        register_detector(thresh)

        # Trend detector
        trend = TrendDetector(
            sudden_change_threshold=2.0,
            persistent_deviation_threshold=0.5,
            window_size=10,
            persistent_ratio=0.7,
        )
        register_detector(trend)

        logger.info(
            "Monitor detectors initialized: threshold, trend (%d total)",
            len(DETECTORS),
        )

    # ---- bus interface ----

    def handle(self, tool: str, args: dict, bstate: Any) -> dict:
        """Handle bus calls (currently: status queries)."""
        if tool == "status":
            return self._get_status(bstate)
        return {"status": "error", "detail": f"Unknown tool: {tool}"}

    def _get_status(self, bstate: Any) -> dict:
        """Return current monitoring status."""
        return {
            "status": "ok",
            "solver_status": bstate.solver_status,
            "ipc_connected": bstate.ipc_connected,
            "has_pose": bstate.has_pose(),
            "detector_count": len(DETECTORS),
        }

    # ---- tick (called from monitor thread at 10 Hz) ----

    def tick(self, bstate: Any, current_sample=None) -> list:
        """
        Run all detectors and return throttled alerts.

        Called at MONITOR_TICK_RATE Hz.

        Args:
            bstate: BState instance.
            current_sample: Current TrajectorySample (or None).

        Returns:
            List of alert dicts that passed throttling (ready for IPC).
        """
        all_alerts = []

        for detector in DETECTORS:
            try:
                alerts = detector.update(current_sample, bstate)
                all_alerts.extend(alerts)
            except Exception as exc:
                logger.exception("Detector '%s' error: %s", detector.name, exc)

        # Apply throttling
        throttled = self._apply_throttle(all_alerts)

        return throttled

    def _apply_throttle(self, alerts: list) -> list:
        """
        Filter alerts through throttling logic.

        - Critical severity: always pass through.
        - Non-critical: pass only if same code hasn't been sent within
          the throttle interval.
        """
        now = time.time()
        passed = []

        with self._throttle_lock:
            for alert in alerts:
                code = alert.get("code", "unknown")
                severity = alert.get("severity", "warning")

                if severity == "critical":
                    # Never throttle critical alerts
                    passed.append(alert)
                    continue

                last_sent = self._throttle_state.get(code, 0.0)
                if (now - last_sent) >= self._throttle_interval:
                    self._throttle_state[code] = now
                    passed.append(alert)
                else:
                    logger.debug(
                        "Throttled alert code=%s (last sent %.1fs ago)",
                        code, now - last_sent,
                    )

        return passed

    def reset_throttle(self) -> None:
        """Reset throttle state (useful in tests)."""
        with self._throttle_lock:
            self._throttle_state.clear()
