"""
Setpoint publisher for Backend B.

Wraps the SetpointAdapter with logging and error handling.
"""

import logging
from typing import Optional

from backend_B.rosbridge.adapter import SetpointAdapter
from backend_B.solver.trajectory import TrajectorySample

logger = logging.getLogger("backend_b.publisher")


class SetpointPublisher:
    """
    Publishes trajectory samples as ROS setpoint messages.

    Delegates to a SetpointAdapter for actual message construction and publishing.
    """

    def __init__(self, adapter: SetpointAdapter):
        """
        Args:
            adapter: SetpointAdapter instance for the current phase.
        """
        self._adapter = adapter
        self._last_sample: Optional[TrajectorySample] = None
        self._publish_count: int = 0

    def publish_sample(self, sample: TrajectorySample) -> None:
        """
        Publish a trajectory sample as a setpoint.

        Args:
            sample: TrajectorySample with pos, vel, yaw.
        """
        try:
            self._adapter.publish_sample(sample)
            self._last_sample = sample
            self._publish_count += 1
        except Exception as exc:
            logger.error("Failed to publish sample: %s", exc)

    def publish_hover(self, pos: list, yaw: float = 0.0) -> None:
        """
        Publish a hover (position hold) setpoint.

        Args:
            pos: [x, y, z] position.
            yaw: Yaw angle in radians.
        """
        try:
            self._adapter.publish_hover(pos, yaw)
        except Exception as exc:
            logger.error("Failed to publish hover: %s", exc)

    def publish_position(self, pos: list, yaw: float = 0.0) -> None:
        """Publish a position setpoint directly."""
        try:
            self._adapter.publish_position(pos, yaw)
        except Exception as exc:
            logger.error("Failed to publish position: %s", exc)

    @property
    def last_sample(self) -> Optional[TrajectorySample]:
        return self._last_sample

    @property
    def publish_count(self) -> int:
        return self._publish_count
