"""
订阅器 — 订阅假无人机位姿/速度/IMU, 加锁写入 BState。
维护 last_data_ts 供监控程序判停产。
"""
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

        # 位姿订阅
        self._subs.append(
            rospy.Subscriber(
                topics["local_position"], PoseStamped, self._on_pose
            )
        )
        # 速度订阅
        self._subs.append(
            rospy.Subscriber(
                topics["local_velocity"], TwistStamped, self._on_velocity
            )
        )
        # IMU 订阅
        self._subs.append(
            rospy.Subscriber(topics["imu_data"], Imu, self._on_imu)
        )
        logger.info("[rosbridge] subscribers ready")

    def _on_pose(self, msg: PoseStamped):
        """位姿回调 — 加锁写 BState pos/quat。"""
        try:
            # ROS Quaternion: x,y,z,w → 接口冻结 [w,x,y,z]
            o = msg.pose.orientation
            quat = [o.w, o.x, o.y, o.z]
            pos = [msg.pose.position.x, msg.pose.position.y, msg.pose.position.z]
            ts = msg.header.stamp.to_sec()
        except Exception as e:
            logger.error(f"[subscriber] pose parse error: {e}")
            return

        with self._state.pose_lock:
            self._state._pose.pos = pos
            self._state._pose.quat = quat
            self._state._pose.ts = ts
            self._state._last_data_ts = time.time()

    def _on_velocity(self, msg: TwistStamped):
        """速度回调 — 加锁写 BState vel。"""
        try:
            vel = [
                msg.twist.linear.x,
                msg.twist.linear.y,
                msg.twist.linear.z,
            ]
            ts = msg.header.stamp.to_sec()
        except Exception as e:
            logger.error(f"[subscriber] velocity parse error: {e}")
            return

        with self._state.pose_lock:
            self._state._pose.vel = vel
            self._state._pose.ts = ts

    def _on_imu(self, msg: Imu):
        """IMU 回调 — 加锁写 BState accel/angular_vel + IMU。"""
        try:
            accel = [
                msg.linear_acceleration.x,
                msg.linear_acceleration.y,
                msg.linear_acceleration.z,
            ]
            angular_vel = [
                msg.angular_velocity.x,
                msg.angular_velocity.y,
                msg.angular_velocity.z,
            ]
            ts = msg.header.stamp.to_sec()
        except Exception as e:
            logger.error(f"[subscriber] imu parse error: {e}")
            return

        with self._state.pose_lock:
            self._state._pose.accel = accel
            self._state._pose.angular_vel = angular_vel
            self._state.update_imu(accel, angular_vel, ts)

    def shutdown(self):
        """取消所有订阅。"""
        for sub in self._subs:
            sub.unregister()
        logger.info("[rosbridge] subscribers unregistered")
