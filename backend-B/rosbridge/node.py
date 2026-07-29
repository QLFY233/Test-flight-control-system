"""
ROS 节点封装 — 初始化 rospy 节点, 封装 publisher/subscriber。
用于 rosbridge 在 B 侧作为 ROS 节点运行。
"""
import logging
import rospy

logger = logging.getLogger(__name__)


def init_node(name: str = "backend_b", anonymous: bool = False):
    """初始化 rospy 节点 (单例, 重复调用安全)。"""
    try:
        rospy.init_node(name, anonymous=anonymous, disable_signals=True)
        logger.info(f"[rosbridge] rospy node '{name}' initialized")
    except rospy.ROSException:
        logger.info("[rosbridge] rospy node already initialized, reusing")


def get_node_name() -> str:
    """获取当前节点名。"""
    try:
        return rospy.get_name()
    except rospy.ROSException:
        return "backend_b"


def is_shutting_down() -> bool:
    """检查 ROS 是否正在关停。"""
    try:
        return rospy.is_shutdown()
    except Exception:
        return True
