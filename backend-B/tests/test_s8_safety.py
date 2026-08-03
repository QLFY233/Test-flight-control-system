#!/usr/bin/env python3
"""
S8.6/S8.8 安全链路测试 — offboard 丢失降级 + ARM 前置告警 (PX4-阶段2-design.md §5.4/§7/§8)。

不依赖真实 ROS master: 在导入 rosbridge.adapter 前向 sys.modules 注入
fake rospy / geometry_msgs / mavros_msgs, 再直接实例化 Phase2Adapter 并注入
fake 状态与方法。

用例:
  ① offboard 丢失重切成功 → 不发 alert、_offboard_lost_at 复位、retries 清零
  ② 重切失败 2 次 → emergency_land 触发 (_emergency 置位) + alert offboard_lost (critical)
  ③ _emergency 下 offboard-lost 不重切 (S8.5 防覆盖)
  ④ preflight ARM 前置 (距 home>2m) 拒绝 → alert preflight_refused (warning) + 返回 False
  ⑤ alert 帧字段齐全 (schema_version/tool/to/payload.level)
  ⑥ send_event 抛异常 → _send_alert 容错 (IPC 未连接场景)
"""
import sys, os, types, time as _real_time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

passed = 0
failed = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} — {detail}")


# ══════════════════════════════════════════════════════════════════
# fake ROS 消息类型 (adapter 导入前注入 sys.modules)
# ══════════════════════════════════════════════════════════════════

class _Point:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x, self.y, self.z = x, y, z

class _Quat:
    def __init__(self, x=0.0, y=0.0, z=0.0, w=1.0):
        self.x, self.y, self.z, self.w = x, y, z, w

class _Vector3:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x, self.y, self.z = x, y, z

class _Header:
    stamp = None
    frame_id = "map"

class _Pose:
    def __init__(self):
        self.position = _Point()
        self.orientation = _Quat()

class _PoseStamped:
    def __init__(self):
        self.header = _Header()
        self.pose = _Pose()

class _Twist:
    def __init__(self):
        self.linear = _Vector3()

_fake_geometry_msg = types.ModuleType("geometry_msgs.msg")
_fake_geometry_msg.PoseStamped = _PoseStamped
_fake_geometry_msg.Twist = _Twist
_fake_geometry_msg.Point = _Point
_fake_geometry_msg.Quaternion = _Quat
_fake_geometry_msg.Vector3 = _Vector3
_fake_geometry = types.ModuleType("geometry_msgs")
_fake_geometry.msg = _fake_geometry_msg
sys.modules["geometry_msgs"] = _fake_geometry
sys.modules["geometry_msgs.msg"] = _fake_geometry_msg

class _FakeSrvResp:
    def __init__(self, ok=True):
        self.success = ok
        self.mode_sent = ok

class _FakeSrv:
    def __call__(self, **kwargs):
        return _FakeSrvResp()

class _FakePublisher:
    def __init__(self, *a, **k):
        self.published = []
    def publish(self, *a, **k):
        self.published.append((a, k))

class _FakeSubscriber:
    def __init__(self, topic, msg_type, cb):
        self.topic = topic
        self.cb = cb

class _FakeTime:
    @staticmethod
    def now():
        return _real_time.time()

_fake_rospy = types.ModuleType("rospy")
_fake_rospy.Publisher = _FakePublisher
_fake_rospy.Subscriber = _FakeSubscriber
_fake_rospy.Time = _FakeTime
_fake_rospy.is_shutdown = lambda: True   # 流/RC 线程立即退出
_fake_rospy.spin = lambda: None
_fake_rospy.wait_for_service = lambda *a, **k: True
_fake_rospy.ServiceProxy = lambda *a, **k: _FakeSrv()
sys.modules["rospy"] = _fake_rospy

class _PositionTarget:
    FRAME_LOCAL_NED = 1
    IGNORE_VX, IGNORE_VY, IGNORE_VZ = 8, 16, 32
    IGNORE_AFX, IGNORE_AFY, IGNORE_AFZ = 64, 128, 256
    IGNORE_YAW_RATE = 2048
    def __init__(self):
        self.header = _Header()
        self.coordinate_frame = 0
        self.type_mask = 0
        self.position = _Point()
        self.yaw = 0.0

class _State:
    def __init__(self):
        self.connected = False
        self.armed = False
        self.mode = ""

class _OverrideRCIn:
    def __init__(self):
        self.channels = []

_fake_mavros_msg = types.ModuleType("mavros_msgs.msg")
_fake_mavros_msg.PositionTarget = _PositionTarget
_fake_mavros_msg.State = _State
_fake_mavros_msg.OverrideRCIn = _OverrideRCIn
_fake_mavros_srv = types.ModuleType("mavros_msgs.srv")
_fake_mavros_srv.CommandBool = type("CommandBool", (), {})
_fake_mavros_srv.SetMode = type("SetMode", (), {})
_fake_mavros = types.ModuleType("mavros_msgs")
_fake_mavros.msg = _fake_mavros_msg
_fake_mavros.srv = _fake_mavros_srv
sys.modules["mavros_msgs"] = _fake_mavros
sys.modules["mavros_msgs.msg"] = _fake_mavros_msg
sys.modules["mavros_msgs.srv"] = _fake_mavros_srv

# 若在 test_all.py 等环境下真 rosbridge 模块已加载 (顶部 import rospy 已绑定真
# rospy), sys.modules 覆盖 fake 不会影响已绑定引用 — 先清缓存强制重载,
# 使 adapter 顶部 import 绑定到 fake rospy/geometry_msgs (本文件可独立运行)。
for _m in ("rosbridge", "rosbridge.adapter", "rosbridge.topics",
           "rosbridge.publisher", "rosbridge.node", "rosbridge.subscriber"):
    sys.modules.pop(_m, None)

import rosbridge.adapter as adapter_mod
from rosbridge.adapter import Phase2Adapter


def _make_adapter(home=None, alerts=None):
    """构造 Phase2Adapter (fake ROS 注入), 跳过虚拟 RC 线程。"""
    a = Phase2Adapter(prefix="/mavros", home=home or [0.0, 0.0, 0.5], state=None)
    a._rc_thread = object()          # 跳过 _start_virtual_rc 真线程
    if alerts is not None:
        a.set_event_sender(alerts.append)
    return a


# ── Test 1: offboard 丢失 → 重切成功 ──
print("\n📋 S8.6-T1: offboard 丢失 → 重切成功 (无 alert, 状态复位)")
alerts = []
a = _make_adapter(alerts=alerts)
a._phase = "ACTIVE"
a._mav_mode = "POSCTL"
a._offboard_lost_at = _real_time.time() - 2.0   # 已过 1s 容忍期
a._offboard_retries = 0
a._call_mode = lambda mode: True
a._wait_mode = lambda mode, timeout=3.0: True
a._check_offboard_lost()
check("重切成功: _offboard_lost_at 复位", a._offboard_lost_at is None)
check("重切成功: _offboard_retries 清零", a._offboard_retries == 0)
check("重切成功: 未触发应急降落", not a._emergency)
check("重切成功: 无 alert 上行", len(alerts) == 0, str(alerts))

# mode 自然恢复 OFFBOARD 也应复位 (防旧状态污染)
a2 = _make_adapter(alerts=[])
a2._phase = "ACTIVE"
a2._mav_mode = "OFFBOARD"
a2._offboard_lost_at = _real_time.time() - 5.0
a2._offboard_retries = 1
a2._call_mode = lambda mode: False
a2._check_offboard_lost()
check("mode 恢复 OFFBOARD: 丢失状态复位", a2._offboard_lost_at is None and a2._offboard_retries == 0)

# ── Test 2: offboard 丢失 → 重切失败 2 次 → 应急降落 + alert ──
print("\n📋 S8.6-T2: offboard 丢失 → 重切失败 2 次 → emergency_land + alert(critical)")
alerts = []
a = _make_adapter(alerts=alerts)
a._phase = "ACTIVE"
a._mav_mode = "POSCTL"
a._offboard_lost_at = _real_time.time() - 2.0
a._offboard_retries = 0
a._call_mode = lambda mode: False
a._wait_mode = lambda mode, timeout=3.0: False
a._check_offboard_lost()
check("第 1 次失败: retries=1", a._offboard_retries == 1, str(a._offboard_retries))
check("第 1 次失败: 未立即应急降落", not a._emergency)
check("第 1 次失败: alert offboard_lost 已发",
      len(alerts) == 1 and alerts[0]["payload"]["code"] == "offboard_lost", str(alerts))
check("第 1 次失败: alert level=critical",
      len(alerts) == 1 and alerts[0]["payload"]["level"] == "critical", str(alerts))
a._check_offboard_lost()
check("第 2 次失败: retries=2", a._offboard_retries == 2, str(a._offboard_retries))
check("第 2 次失败: emergency_land 触发 (_emergency 置位)", a._emergency is True)
check("第 2 次失败: alert 再发 (共 2 条)", len(alerts) == 2, str(alerts))

# ── Test 3: _emergency 下 offboard-lost 不重切 (S8.5 防覆盖) ──
print("\n📋 S8.6-T3: _emergency 下 offboard-lost 不重切 (S8.5 防覆盖)")
alerts = []
a = _make_adapter(alerts=alerts)
a._phase = "ACTIVE"
a._mav_mode = "POSCTL"
a._emergency = True
a._offboard_lost_at = None
a._offboard_retries = 0
mode_calls = []
a._call_mode = lambda mode: mode_calls.append(mode) or True
a._wait_mode = lambda mode, timeout=3.0: True
a._check_offboard_lost()
check("_emergency 下不重切 OFFBOARD", mode_calls == [], str(mode_calls))
check("_emergency 下 _offboard_lost_at 仍 None", a._offboard_lost_at is None)
check("_emergency 下无 alert", len(alerts) == 0, str(alerts))

# ── Test 4: preflight ARM 前置 (距 home>2m) 拒绝 → alert ──
print("\n📋 S8.8-T4: preflight ARM 前置 (距 home>2m) 拒绝 → alert(preflight_refused, warning)")
alerts = []
# home 在 (5,0,0.5), 内部缓存位姿 (0,0,0.5) → dist=5m > 2m (design §7 ARM 前置)
a = _make_adapter(home=[5.0, 0.0, 0.5], alerts=alerts)
a._mav_connected = True
a._mav_mode = "OFFBOARD"
a._mav_armed = True
orig_time = adapter_mod.time
adapter_mod.time = types.SimpleNamespace(time=_real_time.time, sleep=lambda s: None)
try:
    ok = a.preflight(timeout=5.0)
finally:
    adapter_mod.time = orig_time
check("preflight 返回 False (拒绝)", ok is False)
check("alert preflight_refused 已发 (warning)",
      len(alerts) >= 1 and alerts[0]["payload"]["code"] == "preflight_refused"
      and alerts[0]["payload"]["level"] == "warning", str(alerts))
check("alert detail 含 dist 原因",
      len(alerts) >= 1 and "dist to home" in alerts[0]["payload"]["detail"], str(alerts))

# ── Test 5: alert 帧字段齐全 ──
print("\n📋 S8.8-T5: alert 帧字段齐全 (schema_version/tool/to/payload)")
received = []
a = _make_adapter(alerts=received)
a._send_alert("critical", "offboard_lost", "offboard lost (mode=POSCTL), re-engage failed 2/2")
evt = received[0]
check("schema_version == 2", evt.get("schema_version") == 2, str(evt))
check("tool == 'alert'", evt.get("tool") == "alert")
check("to == 'beta' (接口冻结 §3)", evt.get("to") == "beta")
check("msg_type == 'event'", evt.get("msg_type") == "event")
check("payload.level == 'critical'", evt.get("payload", {}).get("level") == "critical")
check("payload.code == 'offboard_lost'", evt.get("payload", {}).get("code") == "offboard_lost")
check("payload.detail 非空", bool(evt.get("payload", {}).get("detail")))
check("payload.ts 与顶层 ts 存在", bool(evt.get("payload", {}).get("ts")) and bool(evt.get("ts")))

# ── Test 6: send_event 抛异常 → _send_alert 容错 (IPC 未连接) ──
print("\n📋 S8.6-T6: send_event 抛异常 → _send_alert 容错 (IPC 未连接)")
a = _make_adapter()
def bad_sender(evt):
    raise RuntimeError("ipc not connected")
a.set_event_sender(bad_sender)
try:
    a._send_alert("warning", "preflight_refused", "mavros not connected within timeout")
    check("send_event 异常被容错 (不向上抛)", True)
except Exception:
    check("send_event 异常被容错 (不向上抛)", False, "异常未捕获")

# ── Summary ──
print(f"\n{'='*50}")
print(f"  S8.6/S8.8 安全链路测试: {passed} 通过 / {passed+failed} 总数")
if failed == 0:
    print("  ✅ 全部通过!")
else:
    print(f"  ❌ {failed} 失败")
print(f"{'='*50}")
sys.exit(0 if failed == 0 else 1)
