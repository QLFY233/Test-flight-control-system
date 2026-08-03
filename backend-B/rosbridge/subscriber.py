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
    """订阅无人机位姿/速度/IMU 话题, 写 BState。

    两阶段默认恒等变换: MAVROS 上行话题已是 ROS ENU/FLU (REP-103,
    frame_id=map/base_link), 不需再变换 — 曾误注 ned_to_enu 造成双重
    变换 (B 侧 z 实为 NED z, 爬升受限, 2026-08-03 ulog 实证 S8.3b)。
    transform 参数保留给未来接入裸 NED 数据源 (design §4.3)。
    """

    def __init__(self, state, prefix: str | None = None,
                 transform=None, quat_transform=None):
        self._state = state
        topics = get_topics(prefix) if prefix else get_topics()
        self._subs = []
        st = state  # 闭包引用
        # 坐标变换 (默认恒等; 仅裸 NED 数据源才需注入, 见类 docstring)
        xform = transform or (lambda x, y, z: (x, y, z))
        qxform = quat_transform or (lambda q: q)

        # 位姿订阅 — 闭包回调
        def on_pose(msg):
            try:
                o = msg.pose.orientation
                quat = qxform([o.w, o.x, o.y, o.z])  # ROS x,y,z,w → [w,x,y,z]
                pos = xform(msg.pose.position.x, msg.pose.position.y, msg.pose.position.z)
                ts = msg.header.stamp.to_sec()
            except Exception:
                return
            with st.pose_lock:
                st._pose.pos = list(pos)
                st._pose.quat = quat
                st._pose.ts = ts
                st._last_data_ts = time.time()
                st._data_received = True

        self._subs.append(rospy.Subscriber(topics["local_position"], PoseStamped, on_pose))

        # 速度订阅
        def on_velocity(msg):
            try:
                vel = xform(msg.twist.linear.x, msg.twist.linear.y, msg.twist.linear.z)
            except Exception:
                return
            with st.pose_lock:
                st._pose.vel = list(vel)
                # B-9: 不覆盖 pose.ts (保持位姿帧时间戳语义), 但刷新停产监测基准
                st._last_data_ts = time.time()
                st._data_received = True

        self._subs.append(rospy.Subscriber(topics["local_velocity"], TwistStamped, on_velocity))

        # IMU 订阅
        def on_imu(msg):
            try:
                accel = xform(msg.linear_acceleration.x, msg.linear_acceleration.y,
                              msg.linear_acceleration.z)
                angular_vel = msg.angular_velocity.x, msg.angular_velocity.y, msg.angular_velocity.z
                ts = msg.header.stamp.to_sec()
            except Exception:
                return
            # B-1 死锁修复: 不再外层持有 pose_lock — update_imu 内部会加锁 (非重入锁),
            # 嵌套获取同一把锁会永久阻塞 (首条 IMU 即挂死)。单次加锁即可同时写 _imu 与 _pose。
            st.update_imu(list(accel), list(angular_vel), ts)

        self._subs.append(rospy.Subscriber(topics["imu_data"], Imu, on_imu))

        logger.info("[rosbridge] subscribers ready")

    def shutdown(self):
        """取消所有订阅。"""
        for sub in self._subs:
            sub.unregister()
        logger.info("[rosbridge] subscribers unregistered")
