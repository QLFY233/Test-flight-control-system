#!/usr/bin/env python3
"""
Fake drone simulator ROS node.

Subscribes to:
  /drone/setpoint_position/local   (geometry_msgs/PoseStamped)

Publishes at 50 Hz:
  /drone/local_position/pose       (geometry_msgs/PoseStamped)
  /drone/local_position/velocity   (geometry_msgs/TwistStamped)
  /drone/imu/data                  (sensor_msgs/Imu)

Features:
  - Kinematic integration: moves toward target at max_speed (default 2 m/s).
  - Boundary self-protection: clamps position to within field boundary.
  - Timeout: if >500 ms without a setpoint, hovers in place.
  - Noise: small Gaussian noise on position for realism (optional).
"""

import math
import time
import random

import rospy
from geometry_msgs.msg import PoseStamped, TwistStamped, Vector3
from sensor_msgs.msg import Imu


class FakeDrone:
    """
    A simple kinematic drone simulator.

    State is integrated at 50 Hz. The drone moves linearly toward the
    current setpoint at max_speed, respecting field boundaries.
    """

    def __init__(self):
        # --- Parameters ---
        self.max_speed = rospy.get_param("~max_speed", 2.0)          # m/s
        self.setpoint_timeout = rospy.get_param("~setpoint_timeout", 0.5)  # seconds
        self.boundary_x = rospy.get_param("~boundary_x", [0.0, 5.0])
        self.boundary_y = rospy.get_param("~boundary_y", [0.0, 4.0])
        self.boundary_z = rospy.get_param("~boundary_z", [0.0, 3.0])
        self.position_noise_std = rospy.get_param("~position_noise_std", 0.01)  # meters
        self.publish_rate = rospy.get_param("~publish_rate", 50.0)   # Hz

        # --- State ---
        # Current drone position [x, y, z] and yaw (radians)
        self.x = 0.0
        self.y = 0.0
        self.z = 0.5   # Start at home height
        self.yaw = 0.0

        # Velocity [vx, vy, vz]
        self.vx = 0.0
        self.vy = 0.0
        self.vz = 0.0

        # Setpoint tracking
        self.target_x = 0.0
        self.target_y = 0.0
        self.target_z = 0.5
        self.target_yaw = 0.0
        self.has_target = False
        self.last_setpoint_time = 0.0

        # --- Publishers ---
        self.pose_pub = rospy.Publisher(
            "/drone/local_position/pose",
            PoseStamped,
            queue_size=10,
        )
        self.vel_pub = rospy.Publisher(
            "/drone/local_position/velocity",
            TwistStamped,
            queue_size=10,
        )
        self.imu_pub = rospy.Publisher(
            "/drone/imu/data",
            Imu,
            queue_size=10,
        )

        # --- Subscriber ---
        self.setpoint_sub = rospy.Subscriber(
            "/drone/setpoint_position/local",
            PoseStamped,
            self._setpoint_callback,
            queue_size=10,
        )

        # --- Timing ---
        self.dt = 1.0 / self.publish_rate
        self.last_time = time.time()

        rospy.loginfo(
            "FakeDrone initialized: max_speed=%.1f m/s, timeout=%.2f s, "
            "boundary_x=%s, boundary_y=%s, boundary_z=%s, rate=%.0f Hz",
            self.max_speed, self.setpoint_timeout,
            self.boundary_x, self.boundary_y, self.boundary_z,
            self.publish_rate,
        )

    # ---- Setpoint subscriber callback ----

    def _setpoint_callback(self, msg):
        """Receive a position setpoint from Backend B."""
        self.target_x = msg.pose.position.x
        self.target_y = msg.pose.position.y
        self.target_z = msg.pose.position.z

        # Extract yaw from quaternion
        qw = msg.pose.orientation.w
        qx = msg.pose.orientation.x
        qy = msg.pose.orientation.y
        qz = msg.pose.orientation.z
        siny_cosp = 2.0 * (qw * qz + qx * qy)
        cosy_cosp = 1.0 - 2.0 * (qy * qy + qz * qz)
        self.target_yaw = math.atan2(siny_cosp, cosy_cosp)

        self.has_target = True
        self.last_setpoint_time = time.time()

    # ---- Main update loop ----

    def update(self):
        """
        Update drone state by one time step (kinematic integration).

        Called at the publish rate (50 Hz).
        """
        now = time.time()

        # Check setpoint timeout
        if self.has_target and (now - self.last_setpoint_time) > self.setpoint_timeout:
            # Timeout: hover in place (target = current position)
            self.target_x = self.x
            self.target_y = self.y
            self.target_z = self.z
            self.target_yaw = self.yaw
            self.has_target = False
            rospy.logdebug("Setpoint timeout, hovering at (%.2f, %.2f, %.2f)",
                           self.x, self.y, self.z)

        # Compute desired velocity (toward target)
        dx = self.target_x - self.x
        dy = self.target_y - self.y
        dz = self.target_z - self.z
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)

        if dist < 0.001:
            # At target: zero velocity
            vx_des = 0.0
            vy_des = 0.0
            vz_des = 0.0
        else:
            # Normalize direction and scale by max_speed
            ndx = dx / dist
            ndy = dy / dist
            ndz = dz / dist
            # If distance < speed * dt, move exactly to target
            speed = min(self.max_speed, dist / self.dt) if self.dt > 0 else self.max_speed
            vx_des = ndx * speed
            vy_des = ndy * speed
            vz_des = ndz * speed

        # Simple velocity integration (instant acceleration for simplicity)
        self.vx = vx_des
        self.vy = vy_des
        self.vz = vz_des

        # Update position
        self.x += self.vx * self.dt
        self.y += self.vy * self.dt
        self.z += self.vz * self.dt

        # Close yaw toward target yaw
        dyaw = self.target_yaw - self.yaw
        while dyaw > math.pi:
            dyaw -= 2.0 * math.pi
        while dyaw < -math.pi:
            dyaw += 2.0 * math.pi
        yaw_rate = 1.0  # rad/s rate of yaw correction
        max_dyaw = yaw_rate * self.dt
        if abs(dyaw) < max_dyaw:
            self.yaw = self.target_yaw
        else:
            self.yaw += math.copysign(max_dyaw, dyaw)

        # Boundary clamp
        self._clamp_to_boundary()

        self.last_time = now

    def _clamp_to_boundary(self):
        """Clamp position to within field boundary."""
        self.x = max(self.boundary_x[0], min(self.boundary_x[1], self.x))
        self.y = max(self.boundary_y[0], min(self.boundary_y[1], self.y))
        self.z = max(self.boundary_z[0], min(self.boundary_z[1], self.z))

    # ---- Publishing ----

    def publish(self):
        """Publish pose, velocity, and IMU messages."""
        now = rospy.Time.now()

        # --- Pose ---
        pose_msg = PoseStamped()
        pose_msg.header.stamp = now
        pose_msg.header.frame_id = "world"

        # Add small noise for realism
        nx = self.x + random.gauss(0.0, self.position_noise_std)
        ny = self.y + random.gauss(0.0, self.position_noise_std)
        nz = self.z + random.gauss(0.0, self.position_noise_std)

        # Re-clamp noisy position
        nx = max(self.boundary_x[0], min(self.boundary_x[1], nx))
        ny = max(self.boundary_y[0], min(self.boundary_y[1], ny))
        nz = max(self.boundary_z[0], min(self.boundary_z[1], nz))

        pose_msg.pose.position.x = nx
        pose_msg.pose.position.y = ny
        pose_msg.pose.position.z = nz

        # Quaternion from yaw (assume zero roll/pitch)
        half_yaw = self.yaw / 2.0
        pose_msg.pose.orientation.w = math.cos(half_yaw)
        pose_msg.pose.orientation.x = 0.0
        pose_msg.pose.orientation.y = 0.0
        pose_msg.pose.orientation.z = math.sin(half_yaw)

        self.pose_pub.publish(pose_msg)

        # --- Velocity ---
        vel_msg = TwistStamped()
        vel_msg.header.stamp = now
        vel_msg.header.frame_id = "world"
        vel_msg.twist.linear.x = self.vx
        vel_msg.twist.linear.y = self.vy
        vel_msg.twist.linear.z = self.vz
        vel_msg.twist.angular.x = 0.0
        vel_msg.twist.angular.y = 0.0
        vel_msg.twist.angular.z = 0.0

        self.vel_pub.publish(vel_msg)

        # --- IMU ---
        imu_msg = Imu()
        imu_msg.header.stamp = now
        imu_msg.header.frame_id = "drone_imu"

        # Orientation same as pose
        imu_msg.orientation.w = math.cos(half_yaw)
        imu_msg.orientation.x = 0.0
        imu_msg.orientation.y = 0.0
        imu_msg.orientation.z = math.sin(half_yaw)

        # Small covariance for orientation
        imu_msg.orientation_covariance = [
            0.01, 0.0, 0.0,
            0.0, 0.01, 0.0,
            0.0, 0.0, 0.01,
        ]

        # Linear acceleration: derived from velocity change (with gravity)
        imu_msg.linear_acceleration.x = 0.0
        imu_msg.linear_acceleration.y = 0.0
        imu_msg.linear_acceleration.z = 9.81

        imu_msg.linear_acceleration_covariance = [
            0.1, 0.0, 0.0,
            0.0, 0.1, 0.0,
            0.0, 0.0, 0.1,
        ]

        # Angular velocity: derived from yaw rate
        imu_msg.angular_velocity.x = 0.0
        imu_msg.angular_velocity.y = 0.0
        imu_msg.angular_velocity.z = 0.0

        imu_msg.angular_velocity_covariance = [
            0.01, 0.0, 0.0,
            0.0, 0.01, 0.0,
            0.0, 0.0, 0.01,
        ]

        self.imu_pub.publish(imu_msg)

    # ---- Main loop ----

    def run(self):
        """Run the fake drone at the configured rate."""
        rate = rospy.Rate(self.publish_rate)
        rospy.loginfo("FakeDrone running at %.1f Hz", self.publish_rate)

        while not rospy.is_shutdown():
            self.update()
            self.publish()
            rate.sleep()


def main():
    rospy.init_node("fake_drone", anonymous=False)
    drone = FakeDrone()
    drone.run()


if __name__ == "__main__":
    main()
