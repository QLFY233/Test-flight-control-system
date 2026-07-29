"""
ROS 消息适配器 — 阶段抽象 (Phase1/Phase2)。
只改配置/前缀, 不动 small_model 上层。
"""
import math
import rospy
from geometry_msgs.msg import PoseStamped, Twist, Point, Quaternion, Vector3

from .topics import get_topics, PHASE1_PREFIX

logger = __import__("logging").getLogger(__name__)


def _yaw_to_quat_msg(yaw: float) -> Quaternion:
    """yaw (rad) → geometry_msgs/Quaternion (x,y,z,w 顺序)。"""
    half = yaw / 2.0
    return Quaternion(
        x=0.0,
        y=0.0,
        z=math.sin(half),
        w=math.cos(half),
    )


class Phase1Adapter:
    """阶段1 假无人机适配器 — /drone 前缀, PoseStamped setpoint。"""

    def __init__(self, prefix: str = PHASE1_PREFIX):
        topics = get_topics(prefix)
        self._pose_pub = rospy.Publisher(
            topics["setpoint_position"], PoseStamped, queue_size=10
        )
        self._vel_pub = rospy.Publisher(
            topics["setpoint_velocity"], Twist, queue_size=10
        )
        logger.info(f"[rosbridge] Phase1Adapter initialized, prefix={prefix}")

    def publish_position(self, pos: list, yaw: float):
        """下发位置 setpoint (PoseStamped)。"""
        msg = PoseStamped()
        msg.header.stamp = rospy.Time.now()
        msg.header.frame_id = "map"
        msg.pose.position = Point(x=pos[0], y=pos[1], z=pos[2])
        msg.pose.orientation = _yaw_to_quat_msg(yaw)
        self._pose_pub.publish(msg)

    def publish_velocity(self, vel: list):
        """下发速度 setpoint (Twist)。"""
        msg = Twist()
        msg.linear = Vector3(x=vel[0], y=vel[1], z=vel[2])
        self._vel_pub.publish(msg)
