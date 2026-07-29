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

rospy.init_node('backend_b', anonymous=False, disable_signals=True)

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

from rosbridge.topics import get_topics
topics = get_topics()
cb_count = [0]
def _make_on_pose(s):
    def cb(msg):
        cb_count[0] += 1
        o = msg.pose.orientation
        with s.pose_lock:
            s._pose.pos = [msg.pose.position.x, msg.pose.position.y, msg.pose.position.z]
            s._pose.quat = [o.w, o.x, o.y, o.z]
            s._pose.ts = msg.header.stamp.to_sec()
            s._last_data_ts = time.time()
    return cb
rospy.Subscriber(topics['local_position'], PoseStamped, _make_on_pose(st))
rospy.Subscriber(topics['local_velocity'], TwistStamped, lambda m: None)
rospy.Subscriber(topics['imu_data'], Imu, lambda m: st.update_imu(
    [m.linear_acceleration.x, m.linear_acceleration.y, m.linear_acceleration.z],
    [m.angular_velocity.x, m.angular_velocity.y, m.angular_velocity.z], m.header.stamp.to_sec()))

threading.Thread(target=ipc.recv_loop, name='ipc', daemon=True).start()
mc.start()
def uplink():
    while True:
        time.sleep(0.1)
        if not st.ipc_connected: continue
        p = st.current_pose
        for tool, payload in [
            ('pose', {'pos':p.pos[:],'quat':p.quat[:],'vel':p.vel[:],'accel':p.accel[:],'angularVel':p.angular_vel[:],'ts':time.time()}),
            ('telemetry', {'accel':p.accel[:],'angularVel':p.angular_vel[:],'ts':time.time()})]:
            msg = {'schema_version':2,'from':'B','to':'alpha','msg_type':'event','tool':tool,'args':{},'payload':payload,'ts':time.time()}
            try: dispatch.send_event(msg)
            except: pass
threading.Thread(target=uplink, name='uplink', daemon=True).start()
print('[B] READY conn={} cb={}'.format(st.ipc_connected, cb_count[0]), flush=True)
rospy.spin()
