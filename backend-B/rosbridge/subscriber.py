"""
订阅器 — 订阅假无人机位姿/速度/IMU, 加锁写入 BState。
维护 last_data_ts 供监控程序判停产。
回调使用闭包而非类方法, 确保 rospy Python 3.8 兼容。
"""
from __future__ import annotations
import time
import logging
import rospy
from geometry_msgs.msg import PoseStamped, TwistStamped
from sensor_msgs.msg import Imu

from .topics import get_topics

logger = logging.getLogger(__name__)


class DroneSubscriber:
    """订阅假无人机 /drone/* 话题, 写 BState。"""

    def __init__(self, state, prefix: str | None = None):
        self._state = state
        topics = get_topics(prefix) if prefix else get_topics()
        self._subs = []
        st = state  # 闭包引用

        # 位姿订阅 — 闭包回调
        def on_pose(msg):
            try:
                o = msg.pose.orientation
                quat = [o.w, o.x, o.y, o.z]  # ROS x,y,z,w → [w,x,y,z]
                pos = [msg.pose.position.x, msg.pose.position.y, msg.pose.position.z]
                ts = msg.header.stamp.to_sec()
            except Exception:
                return
            with st.pose_lock:
                st._pose.pos = pos
                st._pose.quat = quat
                st._pose.ts = ts
                st._last_data_ts = time.time()

        self._subs.append(rospy.Subscriber(topics["local_position"], PoseStamped, on_pose))

        # 速度订阅
        def on_velocity(msg):
            try:
                vel = [msg.twist.linear.x, msg.twist.linear.y, msg.twist.linear.z]
                ts = msg.header.stamp.to_sec()
            except Exception:
                return
            with st.pose_lock:
                st._pose.vel = vel
                st._pose.ts = ts

        self._subs.append(rospy.Subscriber(topics["local_velocity"], TwistStamped, on_velocity))

        # IMU 订阅
        def on_imu(msg):
            try:
                accel = [msg.linear_acceleration.x, msg.linear_acceleration.y, msg.linear_acceleration.z]
                angular_vel = [msg.angular_velocity.x, msg.angular_velocity.y, msg.angular_velocity.z]
                ts = msg.header.stamp.to_sec()
            except Exception:
                return
            with st.pose_lock:
                st._pose.accel = accel
                st._pose.angular_vel = angular_vel
                st.update_imu(accel, angular_vel, ts)

        self._subs.append(rospy.Subscriber(topics["imu_data"], Imu, on_imu))

        logger.info("[rosbridge] subscribers ready")

    def shutdown(self):
        """取消所有订阅。"""
        for sub in self._subs:
            sub.unregister()
        logger.info("[rosbridge] subscribers unregistered")
