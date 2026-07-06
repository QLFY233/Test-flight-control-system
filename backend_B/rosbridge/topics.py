"""
ROS topic constants for Backend B <-> sim-drone communication.

Phase 1 topics use the /drone/* namespace for the fake drone.
"""

# === Phase 1 (fake drone) ===

# Setpoint publishing (B -> drone)
POSE_TOPIC = "/drone/setpoint_position/local"
VEL_TOPIC = "/drone/setpoint_velocity/cmd_vel"

# State subscription (drone -> B)
SUB_POSE_TOPIC = "/drone/local_position/pose"
SUB_VEL_TOPIC = "/drone/local_position/velocity"
SUB_IMU_TOPIC = "/drone/imu/data"

# === Topic QoS defaults ===
# Use standard ROS topic QoS (compatible with fake drone publishing at 50 Hz)
POSE_PUB_QUEUE_SIZE = 10
VEL_PUB_QUEUE_SIZE = 10
SUB_QUEUE_SIZE = 10
