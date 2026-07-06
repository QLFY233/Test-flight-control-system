"""
Trend-based safety detector.

Checks for:
  - Sudden changes: 2nd-order differential of position (jerk-like detection)
  - Persistent deviation: sliding window of tracking error trend
"""

import math
import time
import logging
from collections import deque
from typing import Any, Optional

from backend_B.monitor.detector import Detector, _make_alert

logger = logging.getLogger("backend_b.monitor.trends")


class TrendDetector(Detector):
    """
    Detects safety issues by analyzing trends over a sliding window.
    """

    name = "trend"

    def __init__(
        self,
        sudden_change_threshold: float = 2.0,    # m/s^3 (jerk)
        persistent_deviation_threshold: float = 0.5,  # meters
        window_size: int = 10,
        persistent_ratio: float = 0.7,
    ):
        """
        Args:
            sudden_change_threshold: Jerk magnitude above which to alert.
            persistent_deviation_threshold: Tracking error above which
                persistent deviation is flagged.
            window_size: Number of samples in the sliding window.
            persistent_ratio: Fraction of window samples exceeding threshold
                needed to trigger persistent deviation alert.
        """
        self.sudden_change_threshold = sudden_change_threshold
        self.persistent_deviation_threshold = persistent_deviation_threshold
        self.window_size = window_size
        self.persistent_ratio = persistent_ratio

        # History for jerk detection
        self._position_history: deque = deque(maxlen=3)  # [(x,y,z,t), ...]
        self._velocity_history: deque = deque(maxlen=2)   # [(vx,vy,vz,t), ...]

        # History for persistent deviation
        self._tracking_errors: deque = deque(maxlen=window_size)

    def update(self, sample: Any, bstate: Any) -> list:
        """
        Run trend-based checks and return alerts.

        Args:
            sample: Current TrajectorySample or None.
            bstate: BState instance.

        Returns:
            List of alert dicts.
        """
        alerts = []
        now = time.time()

        current_pose = bstate.current_pose
        if current_pose is None:
            return alerts

        x, y, z = current_pose.x, current_pose.y, current_pose.z

        # --- Sudden change (jerk) detection ---
        alerts.extend(self._check_sudden_change(x, y, z, now))

        # --- Persistent deviation detection ---
        alerts.extend(self._check_persistent_deviation(sample, x, y, z))

        return alerts

    def _check_sudden_change(
        self, x: float, y: float, z: float, now: float,
    ) -> list:
        """
        Detect sudden movement changes using 2nd-order differential (jerk).

        Jerk = d^3(position)/dt^3, approximated as:
          a2 - a1
          --------
             dt
        where a2 = (v2 - v1)/dt, a1 = (v1 - v0)/dt
        """
        alerts = []
        pos_entry = (x, y, z, now)
        self._position_history.append(pos_entry)

        if len(self._position_history) < 3:
            return alerts

        p0 = self._position_history[0]
        p1 = self._position_history[1]
        p2 = self._position_history[2]

        dt1 = p1[3] - p0[3]
        dt2 = p2[3] - p1[3]

        if dt1 < 0.001 or dt2 < 0.001:
            return alerts

        # Velocity at t1
        v1x = (p1[0] - p0[0]) / dt1
        v1y = (p1[1] - p0[1]) / dt1
        v1z = (p1[2] - p0[2]) / dt1

        # Velocity at t2
        v2x = (p2[0] - p1[0]) / dt2
        v2y = (p2[1] - p1[1]) / dt2
        v2z = (p2[2] - p1[2]) / dt2

        # Acceleration change (jerk)
        avg_dt = (dt1 + dt2) / 2.0
        jerk_x = (v2x - v1x) / avg_dt
        jerk_y = (v2y - v1y) / avg_dt
        jerk_z = (v2z - v1z) / avg_dt
        jerk_mag = math.sqrt(jerk_x**2 + jerk_y**2 + jerk_z**2)

        if jerk_mag > self.sudden_change_threshold:
            alerts.append(_make_alert(
                code="sudden_change",
                severity="warning",
                detail=f"Sudden movement detected: jerk={jerk_mag:.2f} m/s^3 > {self.sudden_change_threshold:.2f}",
                detector_name=self.name,
            ))

        return alerts

    def _check_persistent_deviation(
        self, sample: Any, x: float, y: float, z: float,
    ) -> list:
        """
        Check for persistent tracking error over a sliding window.

        If more than persistent_ratio * window_size samples exceed
        persistent_deviation_threshold, a persistent deviation alert is raised.
        """
        alerts = []

        if sample is not None and hasattr(sample, "pos"):
            target = sample.pos
            dx = x - target[0]
            dy = y - target[1]
            dz = z - target[2]
            error = math.sqrt(dx * dx + dy * dy + dz * dz)

            exceeded = 1.0 if error > self.persistent_deviation_threshold else 0.0
            self._tracking_errors.append(exceeded)

            if len(self._tracking_errors) >= self.window_size:
                exceeded_count = sum(self._tracking_errors)
                ratio = exceeded_count / self.window_size

                if ratio >= self.persistent_ratio:
                    alerts.append(_make_alert(
                        code="persistent_deviation",
                        severity="warning",
                        detail=(
                            f"Persistent tracking deviation: "
                            f"{exceeded_count}/{self.window_size} samples "
                            f"(ratio {ratio:.2f}) exceed "
                            f"{self.persistent_deviation_threshold:.2f}m"
                        ),
                        detector_name=self.name,
                    ))

        return alerts

    def reset(self) -> None:
        """Reset all internal state."""
        self._position_history.clear()
        self._velocity_history.clear()
        self._tracking_errors.clear()
