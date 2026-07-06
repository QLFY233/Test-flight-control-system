"""
Threshold-based safety detector.

Checks pose and trajectory data against hard limits defined in the
field config and default constraints.

Alert codes checked:
  - out_of_boundary: drone position outside field boundary
  - ceiling_breach: drone above ceiling
  - floor_breach: drone below floor
  - overspeed: speed exceeds speed_max
  - overaccel: acceleration exceeds accel_max
  - over_angular: angular velocity exceeds angular_velocity_max
  - drone_data_stale: no pose data received for > max_age seconds
  - tracking_error: setpoint-sample distance exceeds threshold
"""

import math
import time
import logging
from typing import Any, Optional

from backend_B.monitor.detector import Detector, _make_alert

logger = logging.getLogger("backend_b.monitor.thresholds")


class ThresholdDetector(Detector):
    """
    Checks drone state against configurable threshold limits.
    """

    name = "threshold"

    def __init__(
        self,
        boundary_x: tuple = None,
        boundary_y: tuple = None,
        boundary_z: tuple = None,
        speed_max: float = 1.5,
        accel_max: float = 2.0,
        angular_velocity_max: float = 0.5,
        ceiling: float = 2.5,
        floor: float = 0.3,
        data_stale_max_age: float = 1.0,
        tracking_error_max: float = 1.0,
    ):
        self.boundary_x = boundary_x or (0.0, 5.0)
        self.boundary_y = boundary_y or (0.0, 4.0)
        self.boundary_z = boundary_z or (0.0, 3.0)
        self.speed_max = speed_max
        self.accel_max = accel_max
        self.angular_velocity_max = angular_velocity_max
        self.ceiling = ceiling
        self.floor = floor
        self.data_stale_max_age = data_stale_max_age
        self.tracking_error_max = tracking_error_max

        # Previous state for deriving velocity/accel
        self._prev_pose: Optional[list] = None  # [x, y, z]
        self._prev_vel: Optional[list] = None   # [vx, vy, vz]
        self._prev_time: Optional[float] = None

    def update(self, sample: Any, bstate: Any) -> list:
        """
        Run all threshold checks and return alerts.

        Args:
            sample: Current TrajectorySample or None.
            bstate: BState instance.

        Returns:
            List of alert dicts.
        """
        alerts = []
        now = time.time()

        # Get current pose
        current_pose = bstate.current_pose
        if current_pose is None:
            return alerts  # No data yet

        x, y, z = current_pose.x, current_pose.y, current_pose.z

        # --- Boundary check ---
        alerts.extend(self._check_boundary(x, y, z))

        # --- Ceiling / floor check ---
        alerts.extend(self._check_altitude(z))

        # --- Data staleness check ---
        alerts.extend(self._check_stale(bstate, now))

        # --- Velocity / acceleration checks ---
        pos = [x, y, z]
        if self._prev_pose is not None and self._prev_time is not None:
            dt = now - self._prev_time
            if dt > 0.001:
                # Compute velocity
                vx = (x - self._prev_pose[0]) / dt
                vy = (y - self._prev_pose[1]) / dt
                vz = (z - self._prev_pose[2]) / dt
                speed = math.sqrt(vx * vx + vy * vy + vz * vz)

                if speed > self.speed_max:
                    alerts.append(_make_alert(
                        code="overspeed",
                        severity="warning",
                        detail=(
                            f"Speed {speed:.2f} m/s exceeds limit "
                            f"{self.speed_max} m/s"
                        ),
                        detector_name=self.name,
                    ))

                # Compute acceleration if we have previous velocity
                if self._prev_vel is not None:
                    ax = (vx - self._prev_vel[0]) / dt
                    ay = (vy - self._prev_vel[1]) / dt
                    az = (vz - self._prev_vel[2]) / dt
                    accel_mag = math.sqrt(ax * ax + ay * ay + az * az)

                    if accel_mag > self.accel_max:
                        alerts.append(_make_alert(
                            code="overaccel",
                            severity="warning",
                            detail=(
                                f"Accel {accel_mag:.2f} m/s^2 exceeds limit "
                                f"{self.accel_max} m/s^2"
                            ),
                            detector_name=self.name,
                        ))

                # Store velocity
                self._prev_vel = [vx, vy, vz]

        # Store previous state
        self._prev_pose = pos
        self._prev_time = now

        # --- Tracking error check ---
        alerts.extend(self._check_tracking_error(sample, pos))

        return alerts

    def _check_boundary(self, x: float, y: float, z: float) -> list:
        """Check position against field boundary."""
        alerts = []

        if x < self.boundary_x[0] or x > self.boundary_x[1]:
            alerts.append(_make_alert(
                code="out_of_boundary",
                severity="critical",
                detail=(
                    f"X={x:.2f} outside boundary "
                    f"[{self.boundary_x[0]:.2f}, {self.boundary_x[1]:.2f}]"
                ),
                detector_name=self.name,
            ))

        if y < self.boundary_y[0] or y > self.boundary_y[1]:
            alerts.append(_make_alert(
                code="out_of_boundary",
                severity="critical",
                detail=(
                    f"Y={y:.2f} outside boundary "
                    f"[{self.boundary_y[0]:.2f}, {self.boundary_y[1]:.2f}]"
                ),
                detector_name=self.name,
            ))

        if z < self.boundary_z[0] or z > self.boundary_z[1]:
            alerts.append(_make_alert(
                code="out_of_boundary",
                severity="critical",
                detail=(
                    f"Z={z:.2f} outside boundary "
                    f"[{self.boundary_z[0]:.2f}, {self.boundary_z[1]:.2f}]"
                ),
                detector_name=self.name,
            ))

        return alerts

    def _check_altitude(self, z: float) -> list:
        """Check altitude against ceiling and floor."""
        alerts = []

        if z > self.ceiling:
            alerts.append(_make_alert(
                code="ceiling_breach",
                severity="warning",
                detail=f"Z={z:.2f} above ceiling {self.ceiling:.2f}",
                detector_name=self.name,
            ))

        if z < self.floor:
            alerts.append(_make_alert(
                code="floor_breach",
                severity="critical",
                detail=f"Z={z:.2f} below floor {self.floor:.2f}",
                detector_name=self.name,
            ))

        return alerts

    def _check_stale(self, bstate: Any, now: float) -> list:
        """Check for stale drone data."""
        alerts = []

        if bstate.data_stale(self.data_stale_max_age):
            alerts.append(_make_alert(
                code="drone_data_stale",
                severity="critical",
                detail=(
                    f"No pose data for {now - bstate.last_data_ts:.1f}s "
                    f"(max {self.data_stale_max_age}s)"
                ),
                detector_name=self.name,
            ))

        return alerts

    def _check_tracking_error(self, sample: Any, pos: list) -> list:
        """Check positional error between setpoint and actual pose."""
        alerts = []

        if sample is not None and hasattr(sample, "pos"):
            target = sample.pos
            dx = pos[0] - target[0]
            dy = pos[1] - target[1]
            dz = pos[2] - target[2]
            error = math.sqrt(dx * dx + dy * dy + dz * dz)

            if error > self.tracking_error_max:
                alerts.append(_make_alert(
                    code="tracking_error",
                    severity="warning",
                    detail=(
                        f"Tracking error {error:.2f}m exceeds "
                        f"limit {self.tracking_error_max:.2f}m"
                    ),
                    detector_name=self.name,
                ))

        return alerts
