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
# rospy.init_node 会用 RotatingFileHandler (~/.ros/log/) 替换 root handlers,
# 吞掉所有非 rospy 日志的 stderr 输出 (2026-08-03 实测: rosbridge/preflight 日志全灭)。
# 补回 stderr handler — 启动脚本 /tmp/backend-b.log 依赖它排障。
import logging as _lg
_stderr_h = _lg.StreamHandler()
_stderr_h.setFormatter(_lg.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s', datefmt='%H:%M:%S'))
_lg.getLogger().addHandler(_stderr_h)

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
from bus.registry import init_registry
init_registry(comp, mc)  # 注册 small_model/monitor 组件 (run_b 此前缺失 → call.action 无法路由)
ipc = IpcClient(st); dispatch = Dispatch(st, ipc)
ipc.set_frame_handler(dispatch.handle_incoming)
comp.set_event_sender(dispatch.send_event); mc.set_event_sender(dispatch.send_event)
ok = ipc.connect()
print('[B] IPC connect: {}'.format(ok), flush=True)

from rosbridge.topics import get_topics, get_phase2_topics
from rosbridge.adapter import make_adapter
import os as _os
PHASE = int(_os.environ.get('PHASE', '1'))
if PHASE == 2:
    topics = get_phase2_topics()
else:
    topics = get_topics()
# 上行恒等变换 (两阶段同): MAVROS 发布的话题本身已是 ROS ENU/FLU 约定
# (REP-103, frame_id=map/base_link, NED→ENU 在 mavros 插件内完成),
# 再施加 ned_to_enu 会造成双重变换 — 2026-08-03 ulog 实证 (S8.3b 根因)。
# 下行 /mavros/setpoint_raw/local 由 mavros 插件负责 ENU→NED (design §4.3),
# Phase2Adapter.publish_position 原样透传 ENU。
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
gp_adapter = make_adapter(PHASE, state=st)
# S8.5: abort → AUTO.LAND 兜底 (design §5.3, 比悬停更保守)
dispatch.set_abort_handler(gp_adapter.emergency_land)
# S8.6/S8.8: adapter alert (offboard_lost/preflight_refused) 上行 → dispatch
# (仅 Phase2 有 offboard 状态机/告警; Phase1 无此方法, 需守卫 — ef50299 引入回归)
if PHASE == 2:
    gp_adapter.set_event_sender(dispatch.send_event)
# S8.4: phase2 land 动作 → AUTO.LAND 兜底 (design §5.3, 与 lifecycle.py 对齐)
if PHASE == 2:
    comp.set_land_handler(gp_adapter.emergency_land)
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
# 主循环: 若 Phase2Adapter 已启动 spin 线程, rospy.spin() 会立即返回,
# 用 while 循环保活主线程 (回调由 spin 线程分发)
try:
    rospy.spin()
except Exception:
    pass
while not rospy.is_shutdown():
    time.sleep(1.0)
