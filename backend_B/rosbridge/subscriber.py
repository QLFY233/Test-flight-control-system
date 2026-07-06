"""
Pose and IMU subscriber for Backend B.

Subscribes to /drone/local_position/pose and /drone/imu/data topics
and updates BState.current_pose with thread-safe locking.
"""

import logging
import threading

logger = logging.getLogger("backend_b.subscriber")


class PoseSubscriber:
    """
    Subscribes to drone pose topics and updates BState.

    Thread-safe: all callbacks use bstate.update_pose() which
    internally acquires the pose_lock.
    """

    def __init__(self, bstate):
        """
        Args:
            bstate: BState instance for thread-safe pose storage.
        """
        import rospy
        from geometry_msgs.msg import PoseStamped, TwistStamped
        from sensor_msgs.msg import Imu
        from backend_B.rosbridge.topics import (
            SUB_POSE_TOPIC, SUB_VEL_TOPIC, SUB_IMU_TOPIC, SUB_QUEUE_SIZE,
        )

        self._bstate = bstate

        # Pose subscriber
        self._pose_sub = rospy.Subscriber(
            SUB_POSE_TOPIC, PoseStamped,
            self._pose_callback,
            queue_size=SUB_QUEUE_SIZE,
        )

        # Velocity subscriber
        self._vel_sub = rospy.Subscriber(
            SUB_VEL_TOPIC, TwistStamped,
            self._vel_callback,
            queue_size=SUB_QUEUE_SIZE,
        )

        # IMU subscriber
        self._imu_sub = rospy.Subscriber(
            SUB_IMU_TOPIC, Imu,
            self._imu_callback,
            queue_size=SUB_QUEUE_SIZE,
        )

        self._pose_count: int = 0
        self._vel_count: int = 0
        self._imu_count: int = 0

        logger.info(
            "PoseSubscriber initialized: pose=%s vel=%s imu=%s",
            SUB_POSE_TOPIC, SUB_VEL_TOPIC, SUB_IMU_TOPIC,
        )

    def _pose_callback(self, msg) -> None:
        """Callback for /drone/local_position/pose."""
        self._bstate.update_pose(msg)
        self._pose_count += 1

    def _vel_callback(self, msg) -> None:
        """Callback for /drone/local_position/velocity (tracking only)."""
        self._vel_count += 1
        # Future: store velocity in bstate for monitoring

    def _imu_callback(self, msg) -> None:
        """Callback for /drone/imu/data (tracking only)."""
        self._imu_count += 1
        # Future: store IMU data in bstate for attitude monitoring

    @property
    def pose_count(self) -> int:
        return self._pose_count

    @property
    def vel_count(self) -> int:
        return self._vel_count

    @property
    def imu_count(self) -> int:
        return self._imu_count

    def shutdown(self) -> None:
        """Unregister all subscribers."""
        self._pose_sub.unregister()
        self._vel_sub.unregister()
        self._imu_sub.unregister()
        logger.info("PoseSubscriber shut down")
