"""
ROS node wrapper for Backend B.

Initializes the ROS node, creates publishers and subscribers.
All calls assume rospy is already imported (ROS1 Noetic).
"""

import logging

logger = logging.getLogger("backend_b.ros_node")


def init_ros_node(name: str = "backend_b") -> None:
    """
    Initialize the ROS node for Backend B.

    Must be called before any publishing or subscribing.
    In ROS1, this must be called on the main thread.

    Args:
        name: ROS node name.
    """
    import rospy
    rospy.init_node(name, anonymous=False, disable_signals=True)
    logger.info("ROS node '%s' initialized", name)


def is_ros_initialized() -> bool:
    """Check if rospy is initialized."""
    try:
        import rospy
        return rospy.core.is_initialized()
    except Exception:
        return False


def get_node_name() -> str:
    """Get the current ROS node name."""
    import rospy
    return rospy.get_name()
