#!/usr/bin/env python3
"""
sim-drone 假无人机节点 (阶段1, schema_version=2)。

运动学模拟：
- 订阅 /drone/setpoint_position/local (PoseStamped) 作为目标位置。
- 线性插值逼近目标点 (速度上限 2 m/s)。
- 50Hz 发布位姿/速度/IMU。
- >500ms 无 setpoint → 自动悬停 (停止移动并维持发布位姿)。
- 目标超出 boundary → 停在边界内最近点 (最后物理安全网)。

用法:
    rosrun sim_drone fake_drone_node.py
    或 launch: roslaunch sim_drone fake_drone.launch
"""

import math
import time
import threading

import rospy
from geometry_msgs.msg import PoseStamped, TwistStamped, Twist, Vector3, Point, Quaternion
from sensor_msgs.msg import Imu


# ── 默认边界 (若 field.yaml 不可用) ──
DEFAULT_BOUNDARY = {"x": [0.0, 5.0], "y": [0.0, 4.0], "z": [0.0, 3.0]}
DEFAULT_SPEED_MAX = 2.0  # m/s
PUBLISH_RATE = 50.0       # Hz
SETPOINT_TIMEOUT = 0.5    # s, 超时自动悬停
MAX_DT = 0.2               # s, 最大积分步长安全兜底

# quaternion 辅助
def _yaw_to_quat(yaw: float) -> tuple:
    """yaw → (w, x, y, z)。"""
    half_yaw = yaw / 2.0
    return (math.cos(half_yaw), 0.0, 0.0, math.sin(half_yaw))


def _clamp(value, min_val, max_val):
    return max(min_val, min(max_val, value))


def _clamp_point(x, y, z, boundary):
    """将 (x, y, z) 夹紧到 boundary 内最近点。"""
    bx = boundary["x"]
    by = boundary["y"]
    bz = boundary["z"]
    return (
        _clamp(x, bx[0], bx[1]),
        _clamp(y, by[0], by[1]),
        _clamp(z, bz[0], bz[1]),
    )


class FakeDrone:
    def __init__(self):
        rospy.init_node("fake_drone", anonymous=False)

        # ── 配置 ──
        self.boundary = DEFAULT_BOUNDARY
        self.speed_max = rospy.get_param("~speed_max", DEFAULT_SPEED_MAX)

        # ── 状态 ──
        self._lock = threading.Lock()
        self.x, self.y, self.z = 0.0, 0.0, 0.5   # 初始位姿
        self.vx, self.vy, self.vz = 0.0, 0.0, 0.0  # 当前速度
        self.yaw = 0.0
        self.target_x, self.target_y, self.target_z = 0.0, 0.0, 0.5
        self.has_target = False
        self.last_setpoint_ts = 0.0
        self.last_time = time.time()

        # ── 发布器 ──
        self.pose_pub = rospy.Publisher("/drone/local_position/pose", PoseStamped, queue_size=10)
        self.vel_pub = rospy.Publisher("/drone/local_position/velocity", TwistStamped, queue_size=10)
        self.imu_pub = rospy.Publisher("/drone/imu/data", Imu, queue_size=10)

        # ── 订阅器 ──
        self.setpoint_sub = rospy.Subscriber(
            "/drone/setpoint_position/local", PoseStamped, self._on_setpoint
        )

        # ── 发布循环 ──
        self._running = True
        self._pub_thread = threading.Thread(target=self._publish_loop, daemon=True)
        self._pub_thread.start()

        rospy.loginfo("[sim-drone] Fake drone ready, boundary=%s speed_max=%.1f", self.boundary, self.speed_max)

    def _on_setpoint(self, msg: PoseStamped):
        """收到新 setpoint。"""
        with self._lock:
            self.target_x = msg.pose.position.x
            self.target_y = msg.pose.position.y
            self.target_z = msg.pose.position.z
            self.has_target = True
            self.last_setpoint_ts = time.time()

    def _publish_loop(self):
        """50Hz 运动学积分 + 发布。"""
        rate = rospy.Rate(PUBLISH_RATE)
        while self._running and not rospy.is_shutdown():
            now = time.time()
            dt = now - self.last_time
            self.last_time = now
            if dt <= 0 or dt > MAX_DT:
                dt = 1.0 / PUBLISH_RATE  # 安全兜底

            with self._lock:
                # ── 超时检测 ──
                if now - self.last_setpoint_ts > SETPOINT_TIMEOUT:
                    # 超时悬停: 目标 = 当前位置
                    self.target_x, self.target_y, self.target_z = self.x, self.y, self.z
                    self.has_target = False

                # ── 夹紧 target 到 boundary (最后物理安全网) ──
                cx, cy, cz = _clamp_point(self.target_x, self.target_y, self.target_z, self.boundary)

                # ── 运动学积分 ──
                dx = cx - self.x
                dy = cy - self.y
                dz = cz - self.z
                dist = math.sqrt(dx * dx + dy * dy + dz * dz)

                if dist < 0.01:
                    # 已到达, 停止
                    self.vx = self.vy = self.vz = 0.0
                    self.x, self.y, self.z = cx, cy, cz
                else:
                    # 线性插值, 限速
                    step = min(self.speed_max * dt, dist)
                    ratio = step / dist if dist > 0 else 0.0
                    self.x += dx * ratio
                    self.y += dy * ratio
                    self.z += dz * ratio
                    self.vx = (dx * ratio) / dt if dt > 0 else 0.0
                    self.vy = (dy * ratio) / dt if dt > 0 else 0.0
                    self.vz = (dz * ratio) / dt if dt > 0 else 0.0

                # ── 偏航旋转 (沿运动方向) ──
                if dist > 0.001:
                    self.yaw = math.atan2(dy, dx)

                # ── 抄出本地副本 (减少锁持有时间) ──
                px, py, pz = self.x, self.y, self.z
                vx, vy, vz = self.vx, self.vy, self.vz
                yaw = self.yaw

            # ── 发布位姿 (ROS geometry_msgs/Quaternion 使用 x,y,z,w 顺序) ──
            # 注意: B 侧 rosbridge 上行 A 时须重排 quat 为 [w,x,y,z] (接口冻结 §3)
            pose_msg = PoseStamped()
            pose_msg.header.stamp = rospy.Time.now()
            pose_msg.header.frame_id = "map"
            pose_msg.pose.position = Point(px, py, pz)
            q = _yaw_to_quat(yaw)
            pose_msg.pose.orientation = Quaternion(q[1], q[2], q[3], q[0])  # x,y,z,w
            self.pose_pub.publish(pose_msg)

            # ── 发布速度 ──
            vel_msg = TwistStamped()
            vel_msg.header.stamp = rospy.Time.now()
            vel_msg.header.frame_id = "map"
            vel_msg.twist.linear = Vector3(vx, vy, vz)
            self.vel_pub.publish(vel_msg)

            # ── 发布 IMU (合成) ──
            imu_msg = Imu()
            imu_msg.header.stamp = rospy.Time.now()
            imu_msg.header.frame_id = "imu_link"
            # 线性加速度 (速度的导数, 简单近似)
            imu_msg.linear_acceleration = Vector3(0.0, 0.0, 9.81)
            # 角速度 (这里简化为零)
            imu_msg.angular_velocity = Vector3(0.0, 0.0, 0.0)
            q_i = _yaw_to_quat(yaw)
            imu_msg.orientation = Quaternion(q_i[1], q_i[2], q_i[3], q_i[0])
            self.imu_pub.publish(imu_msg)

            rate.sleep()

    def shutdown(self):
        self._running = False
        rospy.loginfo("[sim-drone] shutting down")


if __name__ == "__main__":
    drone = FakeDrone()
    try:
        rospy.spin()
    except KeyboardInterrupt:
        pass
    finally:
        drone.shutdown()
