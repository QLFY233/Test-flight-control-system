"""
ROS 话题常量 — 阶段1 假无人机 / 阶段2 PX4 SITL。
话题前缀可切, 换实现只改配置。
"""

# 阶段1: 假无人机
PHASE1_PREFIX = "/drone"

# ── B → 无人机 ──
TOPIC_SETPOINT_POSITION = "/setpoint_position/local"
TOPIC_SETPOINT_VELOCITY = "/cmd_vel"

# ── 无人机 → B ──
TOPIC_LOCAL_POSITION = "/local_position/pose"
TOPIC_LOCAL_VELOCITY = "/local_position/velocity"
TOPIC_IMU_DATA = "/imu/data"


def get_topics(prefix: str = PHASE1_PREFIX) -> dict:
    """返回完整话题名映射。"""
    return {
        "setpoint_position": f"{prefix}{TOPIC_SETPOINT_POSITION}",
        "setpoint_velocity": f"{prefix}{TOPIC_SETPOINT_VELOCITY}",
        "local_position": f"{prefix}{TOPIC_LOCAL_POSITION}",
        "local_velocity": f"{prefix}{TOPIC_LOCAL_VELOCITY}",
        "imu_data": f"{prefix}{TOPIC_IMU_DATA}",
    }

# 阶段2 (PX4 + mavros)  前缀, 远期使用
PHASE2_PREFIX = "/mavros"
