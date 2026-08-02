"""
Backend-B 启动入口 — 由 start_all.sh 调用.
用法: python backend-B/run_b.py
需要先 source ROS 环境.
"""
import os; os.chdir(os.path.dirname(os.path.abspath(__file__)) + '/..')
import sys; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend-B'))
import logging; logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s', datefmt='%H:%M:%S')
import threading, time, rospy
from geometry_msgs.msg import PoseStamped, TwistStamped
from sensor_msgs.msg import Imu

rospy.init_node('backend_b', anonymous=True, disable_signals=True)

from state import BState
from config_loader import load_field, load_constraints
field = load_field('config/field.yaml')
constraints = load_constraints('config/default_constraints.yaml')
st = BState(field, constraints)

from small_model.component import SmallModelComponent
comp = SmallModelComponent(st)
from monitor.component import MonitorComponent
from monitor.detector import DETECTORS, register
from monitor.thresholds import ThresholdDetector
from monitor.trends import TrendDetector
register(ThresholdDetector(st.field, st.default_constraints))
register(TrendDetector())
mc = MonitorComponent(st)

from ipc.client import IpcClient; from ipc.dispatch import Dispatch
ipc = IpcClient(st); dispatch = Dispatch(st, ipc)
ipc.set_frame_handler(dispatch.handle_incoming)
comp.set_event_sender(dispatch.send_event); mc.set_event_sender(dispatch.send_event)
ok = ipc.connect()
print('[B] IPC connect: {}'.format(ok), flush=True)

from rosbridge.topics import get_topics, get_phase2_topics
from rosbridge.adapter import ned_to_enu, ned_quat_to_enu_quat, make_adapter
import os as _os
PHASE = int(_os.environ.get('PHASE', '1'))
if PHASE == 2:
    topics = get_phase2_topics()
    _xf = ned_to_enu; _qxf = ned_quat_to_enu_quat
else:
    topics = get_topics()
    _xf = lambda x, y, z: (x, y, z)
    _qxf = lambda q: q
cb_count = [0]
def _make_on_pose(s):
    def cb(msg):
        cb_count[0] += 1
        o = msg.pose.orientation
        with s.pose_lock:
            s._pose.pos = list(_xf(msg.pose.position.x, msg.pose.position.y, msg.pose.position.z))
            s._pose.quat = _qxf([o.w, o.x, o.y, o.z])
            s._pose.ts = msg.header.stamp.to_sec()
            s._last_data_ts = time.time()
            s._data_received = True
    return cb
rospy.Subscriber(topics['local_position'], PoseStamped, _make_on_pose(st))
# B-2: velocity 真实写入 _pose.vel (原 lambda m: None 直接丢弃 → 上行 vel 恒零, 安全监控失效)
def _on_velocity(msg):
    try:
        with st.pose_lock:
            st._pose.vel = list(_xf(msg.twist.linear.x, msg.twist.linear.y, msg.twist.linear.z))
            st._last_data_ts = time.time()
            st._data_received = True
    except Exception:
        pass
rospy.Subscriber(topics['local_velocity'], TwistStamped, _on_velocity)
# B-2: IMU 走 update_imu (单次加锁同时写 _imu 与 _pose.accel/angular_vel → 上行不再恒零)
rospy.Subscriber(topics['imu_data'], Imu, lambda m: st.update_imu(
    list(_xf(m.linear_acceleration.x, m.linear_acceleration.y, m.linear_acceleration.z)),
    [m.angular_velocity.x, m.angular_velocity.y, m.angular_velocity.z], m.header.stamp.to_sec()))

# 目标点下发 (B-16 对齐 lifecycle: 阶段1/2 均启用 GoalPublisher; 阶段2 先 preflight offboard)
from rosbridge.publisher import GoalPublisher
gp_adapter = make_adapter(PHASE)
if PHASE == 2 and not gp_adapter.preflight(timeout=90.0):
    print('[B] phase2 preflight failed — goal publisher runs without offboard', flush=True)
gp = GoalPublisher(st, comp, gp_adapter, rate=20.0)
gp.start()
print('[B] goal publisher started (PHASE={})'.format(PHASE), flush=True)

threading.Thread(target=ipc.recv_loop, name='ipc', daemon=True).start()
mc.start()
# 断连时显式切 hover (契约 §6: 断连 → small_model 切 hover, 与 lifecycle 路径一致)
def _on_disconnect():
    try:
        comp.handle('hover', {})
        print('[B] IPC disconnected — small_model switched to hover', flush=True)
    except Exception as e:
        print('[B] disconnect hover failed: {}'.format(e), flush=True)
ipc.set_disconnect_handler(_on_disconnect)
def uplink():
    while True:
        time.sleep(0.1)
        if not st.ipc_connected: continue
        p = st.current_pose
        imu = st.current_imu
        for tool, payload in [
            ('pose', {'pos':p.pos[:],'quat':p.quat[:],'vel':p.vel[:],'accel':p.accel[:],'angularVel':p.angular_vel[:],'ts':time.time()}),
            # 🟡-7: 按冻结 payload 补 vel/imu 字段 (保留 angularVel 冗余向后兼容)
            ('telemetry', {'vel':p.vel[:],'accel':imu.accel[:],'angularVel':imu.angular_vel[:],
                           'imu':{'accel':imu.accel[:],'angular_vel':imu.angular_vel[:],'ts':imu.ts},'ts':time.time()})]:
            msg = {'schema_version':2,'from':'B','to':'alpha','msg_type':'event','tool':tool,'args':{},'payload':payload,'ts':time.time()}
            try: dispatch.send_event(msg)
            except Exception as e:  # B-14: 不再静默吞异常
                print('[B] uplink send failed: {}'.format(e), flush=True)
threading.Thread(target=uplink, name='uplink', daemon=True).start()
print('[B] READY conn={} cb={}'.format(st.ipc_connected, cb_count[0]), flush=True)
rospy.spin()
