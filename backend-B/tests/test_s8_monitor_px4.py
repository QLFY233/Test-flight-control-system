#!/usr/bin/env python3
"""
S8 遗留修复测试 — PX4 monitor 适配 (2026-08-03):
  ① overaccel 误报: mavros IMU linear_acceleration 含重力 (≈9.81) →
     monitor 运动加速度 = 速度导数 (悬停/匀速=0), 与 sim-drone 语义一致
  ② out_of_boundary 误报: PX4 home 贴 field boundary 角点 + 噪声 →
     ThresholdDetector 软告警加 margin (默认 0.5m)
  ③ floor_breach 误报: SITL 地面 z 噪声 ~3cm → 豁免提到 5cm
"""
import sys, os, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

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

# ── Test 1: ThresholdDetector boundary margin (S8 遗留 #2) ──
print("\n📋 Test 1: out_of_boundary margin")
from monitor.thresholds import ThresholdDetector

field = {"boundary": {"x": [0.0, 5.0], "y": [0.0, 4.0], "z": [0.0, 3.0]}}
constraints = {"global": {"speed_max": 1.5, "ceiling": 2.5, "floor": 0.3,
                          "accel_max": 2.0, "angular_velocity_max": 0.5}}
det = ThresholdDetector(field, constraints)  # 默认 margin 0.5
sample_base = {"vel": [0, 0, 0], "accel": [0, 0, 0], "angular_vel": [0, 0, 0],
               "pos": [0.1, -0.2, 0.8], "ts": time.time(), "data_received": True}

# PX4 悬停噪声范围 (-0.3~0.3) 在 margin 内 → 不报
alerts = det.update(dict(sample_base, pos=[-0.4, -0.2, 0.8]))
check("悬停噪声 (-0.4,-0.2) 在 margin 内不报",
      all(a["code"] != "out_of_boundary" for a in alerts), str(alerts))
# 超出 margin → 报
alerts = det.update(dict(sample_base, pos=[-0.7, 0.0, 0.8]))
check("(-0.7, 0) 超出 margin 0.5 → 报 out_of_boundary",
      any(a["code"] == "out_of_boundary" for a in alerts), str(alerts))
alerts = det.update(dict(sample_base, pos=[5.6, 2.0, 0.8]))
check("(5.6, 2) 超出 margin → 报", any(a["code"] == "out_of_boundary" for a in alerts))
# margin 可配置
det2 = ThresholdDetector(field, constraints, boundary_margin=0.1)
alerts = det2.update(dict(sample_base, pos=[-0.4, 0.0, 0.8]))
check("margin=0.1 时 (-0.4,0) 报", any(a["code"] == "out_of_boundary" for a in alerts))

# ── Test 2: floor_breach 豁免 5cm (S8 遗留 #3) ──
print("\n📋 Test 2: floor_breach 地面噪声豁免")
alerts = det.update(dict(sample_base, pos=[0.1, 0.1, 0.03]))
check("z=0.03 (SITL 地面噪声) 不报 floor_breach",
      all(a["code"] != "floor_breach" for a in alerts), str(alerts))
alerts = det.update(dict(sample_base, pos=[0.1, 0.1, 0.2]))
check("z=0.2 < floor 0.3 → 报 floor_breach",
      any(a["code"] == "floor_breach" for a in alerts), str(alerts))
# 停机坪常态 z<=0.05 不报 (原 0.01 语义扩展)
alerts = det.update(dict(sample_base, pos=[0.1, 0.1, -0.1]))
check("z=-0.1 (停机坪) 不报", all(a["code"] != "floor_breach" for a in alerts))

# ── Test 3: MonitorComponent 运动加速度 = 速度导数 (S8 遗留 #1) ──
print("\n📋 Test 3: _motion_accel 速度导数")
from config_loader import load_field, load_constraints
from state import BState
from monitor.component import MonitorComponent

field_cfg = load_field(os.path.join(_PROJ_ROOT, "config", "field.yaml"))
constraints_cfg = load_constraints(os.path.join(_PROJ_ROOT, "config", "default_constraints.yaml"))
bs = BState(field_cfg, constraints_cfg["global"])
mc = MonitorComponent(bs)

a0 = mc._motion_accel([0.0, 0.0, 0.0])
check("首帧导数 = 0", a0 == [0.0, 0.0, 0.0], str(a0))
time.sleep(0.11)
a1 = mc._motion_accel([0.0, 0.0, 0.0])
check("悬停 (vel 恒 0) 导数 = 0", max(abs(v) for v in a1) < 1e-9, str(a1))
time.sleep(0.11)
a2 = mc._motion_accel([0.2, 0.0, 0.0])
check("加速 (0→0.2m/s) 导数 > 0", a2[0] > 0.5, str(a2))
time.sleep(0.11)
a3 = mc._motion_accel([0.2, 0.0, 0.0])
check("匀速 (0.2→0.2) 导数 ≈ 0 (死区)", abs(a3[0]) < 1e-9, str(a3))

# ── Test 4: 集成 — PX4 悬停场景无 overaccel/out_of_boundary 误报 ──
print("\n📋 Test 4: PX4 悬停集成 (含重力 IMU 不再误报)")
from bus.protocol import EVENT_TOOL_ALERT
from monitor.detector import register as det_register
# 注册真实阈值检测器 (与 lifecycle._init_bus 一致; 测试独立进程, 注册表无残留)
det_register(ThresholdDetector(field_cfg, constraints_cfg["global"]))
received = []
mc2 = MonitorComponent(bs)
mc2.set_event_sender(lambda evt: received.append(evt) if evt.get("tool") == EVENT_TOOL_ALERT else None)
# 模拟 PX4 悬停: 位置 (0.1,-0.2,0.8), vel 噪声 ±0.05, IMU accel 含重力 9.81
with bs.pose_lock:
    bs._pose.pos = [0.1, -0.2, 0.8]
    bs._pose.vel = [0.0, 0.0, 0.0]
    bs._data_received = True
    bs._last_data_ts = time.time()
for i in range(12):  # 1.2s 模拟 (10Hz)
    with bs.pose_lock:
        bs._pose.vel = [0.03 * (i % 3 - 1), -0.02, 0.0]  # 悬停微噪声
    mc2._tick()
    time.sleep(0.02)
codes = [e["payload"]["code"] for e in received]
check("悬停 1.2s 无 overaccel 误报", "overaccel" not in codes, str(codes))
check("悬停 1.2s 无 out_of_boundary 误报", "out_of_boundary" not in codes, str(codes))
check("悬停 1.2s 无 floor_breach 误报", "floor_breach" not in codes, str(codes))

# 真实越界仍检测: 移到 (-1.0, 0) → 报 out_of_boundary
with bs.pose_lock:
    bs._pose.pos = [-1.0, 0.0, 0.8]
mc2._tick()
codes = [e["payload"]["code"] for e in received]
check("真越界 (-1,0) 仍报 out_of_boundary", "out_of_boundary" in codes, str(codes))

# ── Test 5: hover 夹紧 (PX4 home 贴 boundary 角点适配, 2026-08-03) ──
print("\n📋 Test 5: stub hover 夹紧 (界外悬停不再 reject)")
from small_model.stub import StubGoalGenerator
from small_model.goal_gen import make_goal_generator, GoalGenError

sg = StubGoalGenerator()
sg._home = [0.0, 0.0, 0.5]
safety = {"boundary": [[0, 0, 0], [5, 4, 3]], "ceiling": 2.5, "floor": 0.3, "speed_max": 1.5}
# PX4 场景: 悬停在 home (0,0) 附近, y 微负 (贴边噪声)
pose = {"pos": [0.0, -0.1, 0.87], "quat": [1, 0, 0, 0], "vel": [0, 0, 0], "yaw": 0.0}
g = sg.generate({"code": "hover"}, pose, {}, safety)
check("hover 界外 (-0.1) 夹紧到 y=0 不 reject", g["goal"][1] == 0.0 and abs(g["goal"][0]) < 1e-9, str(g))
# 界内 hover 原样
pose2 = {"pos": [1.0, 2.0, 0.87], "quat": [1, 0, 0, 0], "vel": [0, 0, 0], "yaw": 0.0}
g2 = sg.generate({"code": "hover"}, pose2, {}, safety)
check("hover 界内 (1,2) 原样", g2["goal"] == [1.0, 2.0, 0.87], str(g2))
# 界外较远 → 夹到边界内最近点
pose3 = {"pos": [-1.0, 5.5, 0.87], "quat": [1, 0, 0, 0], "vel": [0, 0, 0], "yaw": 0.0}
g3 = sg.generate({"code": "hover"}, pose3, {}, safety)
check("hover (-1,5.5) 夹到 (0,4)", g3["goal"][0] == 0.0 and g3["goal"][1] == 4.0, str(g3))

# ── Summary ──
print(f"\n{'='*50}")
print(f"  PX4 monitor 适配测试: {passed} 通过 / {passed+failed} 总数")
if failed == 0:
    print("  ✅ 全部通过!")
else:
    print(f"  ❌ {failed} 失败")
print(f"{'='*50}")
sys.exit(0 if failed == 0 else 1)
