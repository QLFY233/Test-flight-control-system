"""
Phase abstraction for setpoint publishing.

The SetpointAdapter allows Backend B to work with different drone
interfaces. Phase 1 uses /drone/* topics; future phases can use
different topic names or message types.
"""

from abc import ABC, abstractmethod
from typing import Optional


class SetpointAdapter(ABC):
    """Abstract base for setpoint publishing."""

    @abstractmethod
    def publish_position(self, pos: list, yaw: float) -> None:
        """Publish a position setpoint (x, y, z meters, yaw radians)."""
        ...

    @abstractmethod
    def publish_velocity(self, vel: list) -> None:
        """Publish a velocity setpoint (vx, vy, vz m/s)."""
        ...

    @abstractmethod
    def publish_hover(self, pos: list, yaw: float) -> None:
        """Publish a hover (position hold) setpoint."""
        ...

    @abstractmethod
    def publish_sample(self, sample) -> None:
        """Publish a TrajectorySample as setpoint."""
        ...


class Phase1Adapter(SetpointAdapter):
    """
    Phase 1 adapter: publishes to /drone/* topics as PoseStamped messages.

    Uses raw rospy publishers to avoid extra dependencies.
    """

    def __init__(self):
        import rospy
        from geometry_msgs.msg import PoseStamped
        from backend_B.rosbridge.topics import POSE_TOPIC, POSE_PUB_QUEUE_SIZE

        self._pose_pub = rospy.Publisher(
            POSE_TOPIC, PoseStamped, queue_size=POSE_PUB_QUEUE_SIZE,
        )
        self._PoseStamped = PoseStamped
        logger = __import__("logging").getLogger("backend_b.ros_adapter")
        logger.info("Phase1Adapter initialized on topic %s", POSE_TOPIC)

    def publish_position(self, pos: list, yaw: float) -> None:
        """Publish a position setpoint as PoseStamped."""
        import math
        import rospy

        msg = self._PoseStamped()
        msg.header.stamp = rospy.Time.now()
        msg.header.frame_id = "world"
        msg.pose.position.x = pos[0]
        msg.pose.position.y = pos[1]
        msg.pose.position.z = pos[2]

        # Convert yaw to quaternion
        half_yaw = yaw / 2.0
        msg.pose.orientation.w = math.cos(half_yaw)
        msg.pose.orientation.x = 0.0
        msg.pose.orientation.y = 0.0
        msg.pose.orientation.z = math.sin(half_yaw)

        self._pose_pub.publish(msg)

    def publish_velocity(self, vel: list) -> None:
        """Publish velocity (for now, via position topic with velocity-based hack).

        In Phase 1 with fake drone, velocity control is indirect.
        We publish position and let the fake drone's kinematics handle it.
        """
        # Phase 1 does not support direct velocity publishing;
        # the fake drone moves toward position setpoints with max_speed.
        pass

    def publish_hover(self, pos: list, yaw: float) -> None:
        """Publish a hover (position hold) setpoint."""
        self.publish_position(pos, yaw)

    def publish_sample(self, sample) -> None:
        """Publish a TrajectorySample as PoseStamped setpoint."""
        self.publish_position(sample.pos, sample.yaw)
