"""
Solver component: the bus-facing interface for trajectory execution.

Registered as "solver" in the bus registry. Handles:
  - tool="trajectory": translate spec, generate continuous trajectory,
    collision check, set as current trajectory
  - tool="abort": clear current trajectory, issue hover
  - tool="hover": generate hover at current pose or home

The solver tick (called at 20 Hz from a dedicated thread):
  - Advances the trajectory by one sample
  - Re-checks the sample for collisions (online safety)
  - Publishes the setpoint via the adapter
"""

import time
import logging
import threading
from typing import Optional

from backend_B.solver.translator import translate_spec, TrajectoryPlan
from backend_B.solver.trajectory import (
    generate_trajectory,
    hover_trajectory,
    ContinuousTrajectory,
    TrajectorySample,
)
from backend_B.solver.collision import check_trajectory

logger = logging.getLogger("backend_b.solver")

# Tick rate for the solver loop
SOLVER_TICK_RATE = 20.0  # Hz
SOLVER_TICK_INTERVAL = 1.0 / SOLVER_TICK_RATE


class SolverComponent:
    """
    Bus component that manages trajectory generation and execution.

    Lifecycle:
    1. Receives a trajectory spec via handle("trajectory", ...)
    2. Translates it, generates a ContinuousTrajectory
    3. tick() advances the trajectory at SOLVER_TICK_RATE Hz
    4. Publishes setpoints via the SetpointAdapter
    """

    def __init__(self, default_constraints: dict):
        self._default_constraints = default_constraints
        self._current_trajectory: Optional[ContinuousTrajectory] = None
        self._current_plan: Optional[TrajectoryPlan] = None
        self._sample_index: int = 0
        self._status: str = "idle"  # idle | executing | hovering | aborted
        self._lock = threading.Lock()

    # ---- bus interface (called from IPC thread) ----

    def handle(self, tool: str, args: dict, bstate) -> dict:
        """
        Handle a bus call.

        Args:
            tool: Tool name ("trajectory", "abort", "hover").
            args: Tool arguments dict.
            bstate: BState instance for current state access.

        Returns:
            Result dict with "status" and optional "detail" / "task_id".
        """
        if tool == "trajectory":
            return self._handle_trajectory(args, bstate)
        elif tool == "abort":
            return self._handle_abort(args, bstate)
        elif tool == "hover":
            return self._handle_hover(args, bstate)
        else:
            return {"status": "error", "detail": f"Unknown tool: {tool}"}

    def _handle_trajectory(self, args: dict, bstate) -> dict:
        """Process a new trajectory command."""
        try:
            plan = translate_spec(args, self._default_constraints)
        except ValueError as e:
            logger.warning("Invalid trajectory spec: %s", e)
            return {"status": "reject", "detail": str(e)}

        if not plan.has_remaining():
            return {"status": "reject", "detail": "Empty trajectory (no segments)"}

        # Generate continuous trajectory
        trajectory = generate_trajectory(
            plan,
            self._default_constraints,
            tick_rate=SOLVER_TICK_RATE,
        )

        if trajectory.is_empty():
            return {"status": "reject", "detail": "Generated empty trajectory"}

        # Offline collision check
        collision_samples = []
        for i, sample in enumerate(trajectory.samples):
            collision_samples.append({
                "pos": sample.pos,
                "segment_index": 0,
            })

        bstate_field = bstate.field
        keep_clear = self._default_constraints.get("keep_clear_distance", 0.5)

        if bstate_field is not None:
            collisions = check_trajectory(collision_samples, bstate_field, keep_clear)
            if collisions:
                logger.warning(
                    "Trajectory %s rejected: %d collision(s) detected offline",
                    plan.task_id, len(collisions),
                )
                return {
                    "status": "reject",
                    "detail": f"Collision detected: {collisions[0]['reason']}",
                    "collisions": collisions,
                }

        # Accept trajectory
        with self._lock:
            self._current_trajectory = trajectory
            self._current_plan = plan
            self._sample_index = 0
            self._status = "executing"

        bstate.solver_status = "executing"
        bstate.current_trajectory = trajectory

        logger.info(
            "Trajectory %s accepted: %d samples, %.2fs duration",
            plan.task_id, trajectory.sample_count(), trajectory.total_duration,
        )

        return {
            "status": "ok",
            "task_id": plan.task_id,
            "sample_count": trajectory.sample_count(),
            "total_duration": trajectory.total_duration,
        }

    def _handle_abort(self, args: dict, bstate) -> dict:
        """Abort the current trajectory."""
        with self._lock:
            had_trajectory = self._current_trajectory is not None
            self._current_trajectory = None
            self._current_plan = None
            self._sample_index = 0
            self._status = "aborted"

        bstate.solver_status = "aborted"
        bstate.current_trajectory = None

        logger.info("Trajectory aborted%s", " (was active)" if had_trajectory else "")

        # Generate hover at current position or home
        current_pos = bstate.get_position()
        if current_pos:
            hover_traj = hover_trajectory(current_pos)
            with self._lock:
                self._current_trajectory = hover_traj
                self._sample_index = 0
                self._status = "hovering"
            bstate.solver_status = "hovering"
            bstate.current_trajectory = hover_traj

        return {"status": "ok", "detail": "aborted"}

    def _handle_hover(self, args: dict, bstate) -> dict:
        """Enter hover at a specified position or current pose."""
        target = args.get("position", None)

        if target is None:
            # Hover at current position
            current = bstate.get_position()
            if current is None:
                # Fall back to home
                if bstate.field:
                    target = list(bstate.field.home)
                    yaw = bstate.field.home_yaw
                else:
                    return {"status": "error", "detail": "No current pose and no field loaded"}
            else:
                target = current
                yaw = bstate.get_yaw() or 0.0
        else:
            yaw = args.get("yaw", 0.0)

        pose_with_yaw = list(target) + [yaw]
        hover_traj = hover_trajectory(pose_with_yaw)

        with self._lock:
            self._current_trajectory = hover_traj
            self._current_plan = None
            self._sample_index = 0
            self._status = "hovering"

        bstate.solver_status = "hovering"
        bstate.current_trajectory = hover_traj

        logger.info("Hovering at %s", target)
        return {"status": "ok", "detail": "hovering", "position": target}

    # ---- tick (called from solver thread at 20 Hz) ----

    def tick(self, bstate, adapter) -> list:
        """
        Advance the trajectory by one sample and publish the setpoint.

        Called at SOLVER_TICK_RATE Hz from the solver thread.

        Args:
            bstate: BState instance.
            adapter: SetpointAdapter for publishing.

        Returns:
            List of event dicts to send to Backend A (empty if nothing to report).
        """
        events = []

        with self._lock:
            traj = self._current_trajectory
            idx = self._sample_index

            if traj is None or idx >= traj.sample_count():
                # No active trajectory: publish hover at current position
                self._status = "idle"
                bstate.solver_status = "idle"
                current = bstate.get_position()
                if current:
                    adapter.publish_hover(current, bstate.get_yaw() or 0.0)
                return events

            sample = traj.get_sample(idx)
            if sample is None:
                return events

            # Online collision re-check
            if bstate.field is not None:
                collision_sample = [{
                    "pos": sample.pos,
                    "segment_index": 0,
                }]
                keep_clear = self._default_constraints.get("keep_clear_distance", 0.5)
                collisions = check_trajectory(collision_sample, bstate.field, keep_clear)
                if collisions:
                    logger.warning(
                        "Online collision detected at sample %d: %s",
                        idx, collisions[0]["reason"],
                    )
                    # Emergency: abort trajectory
                    self._current_trajectory = None
                    self._current_plan = None
                    self._sample_index = 0
                    self._status = "aborted"
                    bstate.solver_status = "aborted"
                    bstate.current_trajectory = None

                    events.append({
                        "event": "alert",
                        "data": {
                            "code": "collision_online",
                            "severity": "critical",
                            "detail": collisions[0]["reason"],
                        },
                    })

                    # Hover in place
                    current = bstate.get_position()
                    if current:
                        adapter.publish_hover(current, bstate.get_yaw() or 0.0)
                    return events

            # Publish the setpoint
            adapter.publish_sample(sample)

            # Advance
            self._sample_index = idx + 1

            # Check if trajectory is complete
            if self._sample_index >= traj.sample_count():
                logger.info(
                    "Trajectory %s complete (%d samples)",
                    traj.task_id, traj.sample_count(),
                )
                self._current_trajectory = None
                self._current_plan = None
                self._sample_index = 0
                self._status = "idle"
                bstate.solver_status = "idle"
                bstate.current_trajectory = None

                events.append({
                    "event": "trajectory_complete",
                    "data": {
                        "task_id": traj.task_id,
                        "sample_count": traj.sample_count(),
                    },
                })

            # Update bstate tracking
            bstate.current_segment_index = 0  # Simplified; full impl would track segments

        return events

    @property
    def status(self) -> str:
        with self._lock:
            return self._status

    @property
    def current_trajectory(self) -> Optional[ContinuousTrajectory]:
        with self._lock:
            return self._current_trajectory
