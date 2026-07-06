"""
Continuous trajectory generation for Backend B solver.

Generates sampled trajectories with:
  - Trapezoidal velocity profile (accelerate -> cruise -> decelerate)
  - Linear position interpolation between waypoints
  - Yaw linear interpolation
  - Sampling at the solver tick rate (default 20 Hz)
"""

import math
import uuid
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TrajectorySample:
    """A single sample point on a continuous trajectory."""
    t: float          # Time offset in seconds from trajectory start
    pos: list         # [x, y, z]
    vel: list         # [vx, vy, vz]
    accel: list       # [ax, ay, az]
    yaw: float        # radians


@dataclass
class ContinuousTrajectory:
    """A continuous trajectory with uniform sampling."""
    task_id: str
    samples: list        # list[TrajectorySample]
    total_duration: float
    segment_boundaries: list  # cumulative time at each segment end

    def is_empty(self) -> bool:
        return len(self.samples) == 0

    def sample_count(self) -> int:
        return len(self.samples)

    def get_sample(self, index: int) -> Optional[TrajectorySample]:
        """Get a sample by index, or None if out of range."""
        if 0 <= index < len(self.samples):
            return self.samples[index]
        return None


def generate_trajectory(
    plan,
    default_constraints: dict,
    tick_rate: float = 20.0,
) -> ContinuousTrajectory:
    """
    Generate a sampled continuous trajectory from a TrajectoryPlan.

    For each segment:
    1. Compute the distance between waypoints.
    2. Apply trapezoidal velocity profile:
       - Accelerate at accel_max from 0 to speed_max
       - Cruise at speed_max
       - Decelerate at accel_max to 0
    3. Linear interpolation of position: p(t) = p_start + (t/dur) * (p_end - p_start)
    4. Linear interpolation of yaw.
    5. Sample at tick_rate Hz.

    Each segment starts from zero velocity and ends at zero velocity.
    Waypoint arrival times are exact.

    Args:
        plan: TrajectoryPlan with segments and global_constraints.
        default_constraints: System default constraints.
        tick_rate: Sampling frequency in Hz.

    Returns:
        ContinuousTrajectory with sampled points.
    """
    dt = 1.0 / tick_rate
    all_samples = []
    segment_boundaries = []
    cumulative_t = 0.0

    for seg_idx, segment in enumerate(plan.segments):
        # Resolve constraints for this segment
        from backend_B.solver.constraints import resolve_constraints, constraints_to_dict
        constraints = resolve_constraints(
            point_c=segment.get("constraints", {}),
            segment_c=segment.get("segment_constraints", {}),
            global_c=plan.global_constraints,
            default_c=constraints_to_dict(
                speed_max=default_constraints.get("speed_max", 1.5),
                accel_max=default_constraints.get("accel_max", 2.0),
                angular_velocity_max=default_constraints.get("angular_velocity_max", 0.5),
                keep_clear_distance=default_constraints.get("keep_clear_distance", 0.5),
                ceiling=default_constraints.get("ceiling", 2.5),
                floor=default_constraints.get("floor", 0.3),
            ),
        )

        speed_max = constraints.get("speed_max", 1.5)
        accel_max = constraints.get("accel_max", 2.0)

        # Get start and end waypoints
        wp_start = segment["from"]
        wp_end = segment["to"]

        sx, sy, sz = wp_start["x"], wp_start["y"], wp_start["z"]
        ex, ey, ez = wp_end["x"], wp_end["y"], wp_end["z"]

        yaw_start = wp_start.get("yaw", 0.0)
        yaw_end = wp_end.get("yaw", 0.0)

        # Compute 3D distance
        dist = math.sqrt((ex - sx) ** 2 + (ey - sy) ** 2 + (ez - sz) ** 2)

        if dist < 1e-6:
            # Zero-length segment: single sample at the waypoint
            sample = TrajectorySample(
                t=cumulative_t,
                pos=[sx, sy, sz],
                vel=[0.0, 0.0, 0.0],
                accel=[0.0, 0.0, 0.0],
                yaw=yaw_end,
            )
            all_samples.append(sample)
            segment_boundaries.append(cumulative_t)
            continue

        # ---- Trapezoidal velocity profile ----

        # Check if we can reach max speed before needing to decelerate
        # Time to accelerate to max speed: t_accel = speed_max / accel_max
        # Distance covered during acceleration: d_accel = 0.5 * accel_max * t_accel^2
        # Two acceleration phases (accel + decel) cover: 2 * d_accel = speed_max^2 / accel_max
        t_accel = speed_max / accel_max
        d_accel = 0.5 * accel_max * t_accel * t_accel

        two_phase_dist = 2.0 * d_accel  # distance for accel-decel (no cruise)

        if two_phase_dist >= dist:
            # Triangular profile: we never reach max speed
            # Peak speed: v_peak = sqrt(dist * accel_max)
            v_peak = math.sqrt(dist * accel_max)
            t_ramp = v_peak / accel_max
            phase_durations = [t_ramp, 0.0, t_ramp]  # accel, cruise, decel
        else:
            # Full trapezoidal: accel, cruise, decel
            # Cruise distance = dist - 2 * d_accel
            d_cruise = dist - two_phase_dist
            t_cruise = d_cruise / speed_max
            phase_durations = [t_accel, t_cruise, t_accel]

        t_accel_phase, t_cruise, t_decel_phase = phase_durations
        total_segment_t = t_accel_phase + t_cruise + t_decel_phase

        # Compute direction vector (unit)
        ux = (ex - sx) / dist
        uy = (ey - sy) / dist
        uz = (ez - sz) / dist

        # Sample the segment
        t = 0.0
        while t <= total_segment_t + 1e-9:
            global_t = cumulative_t + t

            # Determine which phase we're in
            if t <= t_accel_phase:
                # Acceleration phase: s = 0.5 * a * t^2, v = a * t
                a_local = accel_max
                v_local = a_local * t
                s_local = 0.5 * a_local * t * t
            elif t <= t_accel_phase + t_cruise:
                # Cruise phase: constant velocity
                t_in_cruise = t - t_accel_phase
                a_local = 0.0
                v_local = speed_max
                s_local = d_accel + speed_max * t_in_cruise
            else:
                # Deceleration phase
                t_in_decel = t - t_accel_phase - t_cruise
                a_local = -accel_max
                v_local = speed_max - accel_max * t_in_decel
                s_local = d_accel + speed_max * t_cruise
                s_local += speed_max * t_in_decel - 0.5 * accel_max * t_in_decel * t_in_decel

            # Clamp
            s_local = min(s_local, dist)
            v_local = max(v_local, 0.0)

            # Position
            px = sx + s_local * ux
            py = sy + s_local * uy
            pz = sz + s_local * uz

            # Velocity vector
            vx = v_local * ux
            vy = v_local * uy
            vz = v_local * uz

            # Acceleration vector
            ax = a_local * ux
            ay = a_local * uy
            az = a_local * uz

            # Yaw linear interpolation
            dyaw = yaw_end - yaw_start
            # Normalize to [-pi, pi]
            while dyaw > math.pi:
                dyaw -= 2.0 * math.pi
            while dyaw < -math.pi:
                dyaw += 2.0 * math.pi
            fraction = s_local / dist if dist > 0 else 1.0
            yaw = yaw_start + fraction * dyaw

            sample = TrajectorySample(
                t=global_t,
                pos=[px, py, pz],
                vel=[vx, vy, vz],
                accel=[ax, ay, az],
                yaw=yaw,
            )
            all_samples.append(sample)

            t += dt

        # Ensure the final point is included exactly
        if total_segment_t > 0 and all_samples:
            last = all_samples[-1]
            # Check if last sample is not at the end position
            last_dist_to_end = math.sqrt(
                (last.pos[0] - ex) ** 2 + (last.pos[1] - ey) ** 2 + (last.pos[2] - ez) ** 2
            )
            if last_dist_to_end > 1e-3:
                final_sample = TrajectorySample(
                    t=cumulative_t + total_segment_t,
                    pos=[ex, ey, ez],
                    vel=[0.0, 0.0, 0.0],
                    accel=[0.0, 0.0, 0.0],
                    yaw=_normalize_angle(yaw_end),
                )
                all_samples.append(final_sample)

        cumulative_t += total_segment_t
        segment_boundaries.append(cumulative_t)

    # Deduplicate samples at the same timestamp (segment boundaries)
    deduped = _deduplicate_samples(all_samples)

    return ContinuousTrajectory(
        task_id=plan.task_id,
        samples=deduped,
        total_duration=cumulative_t,
        segment_boundaries=segment_boundaries,
    )


def hover_trajectory(pose: list, task_id: str = None) -> ContinuousTrajectory:
    """
    Generate a single-point zero-velocity hover trajectory at the given pose.

    Args:
        pose: [x, y, z, yaw] or [x, y, z, qw, qx, qy, qz].
              If 7 elements, yaw is extracted from the quaternion.
        task_id: Optional task identifier (auto-generated if not provided).

    Returns:
        ContinuousTrajectory with one sample.
    """
    if task_id is None:
        task_id = f"hover-{uuid.uuid4().hex[:8]}"

    if len(pose) >= 7:
        x, y, z = pose[0], pose[1], pose[2]
        # Extract yaw from quaternion
        qw, qx, qy, qz = pose[3], pose[4], pose[5], pose[6]
        siny_cosp = 2.0 * (qw * qz + qx * qy)
        cosy_cosp = 1.0 - 2.0 * (qy * qy + qz * qz)
        yaw = math.atan2(siny_cosp, cosy_cosp)
    elif len(pose) >= 4:
        x, y, z, yaw = pose[0], pose[1], pose[2], pose[3]
    else:
        x, y, z = pose[0], pose[1], pose[2]
        yaw = 0.0

    sample = TrajectorySample(
        t=0.0,
        pos=[x, y, z],
        vel=[0.0, 0.0, 0.0],
        accel=[0.0, 0.0, 0.0],
        yaw=yaw,
    )

    return ContinuousTrajectory(
        task_id=task_id,
        samples=[sample],
        total_duration=0.0,
        segment_boundaries=[0.0],
    )


def _normalize_angle(angle: float) -> float:
    """Normalize an angle to [-pi, pi]."""
    while angle > math.pi:
        angle -= 2.0 * math.pi
    while angle < -math.pi:
        angle += 2.0 * math.pi
    return angle


def _deduplicate_samples(samples: list) -> list:
    """Remove consecutive samples with identical timestamps."""
    if not samples:
        return samples

    result = [samples[0]]
    for s in samples[1:]:
        if abs(s.t - result[-1].t) > 1e-9:
            result.append(s)
    return result
