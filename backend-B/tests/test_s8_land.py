#!/usr/bin/env python3
"""
后端 B 功能测试 — S8.4 land → AUTO.LAND (PX4-阶段2-design.md §5.3/§8 S8.4)

验证 SmallModelComponent 的 land 兜底回调机制:
  ① 默认 (未注入 handler, phase1) land 动作仍生成 stub 下压 goal — 零回归
  ② 注入 handler (phase2) 后 land 动作不生成 goal、plan 标记完成、发 completed 事件
  ③ handler 在锁外被调用一次 (不得持 self._lock 执行)
  ④ 非 land 动作 (takeoff) 不受 handler 影响, 仍生成 goal
  ⑤ 推进路径 (check_arrival_and_advance → _advance_action) 命中 land 同样触发 handler

Python 3.8 兼容 (venv-B)。不依赖真实 ROS/roscore, 全部使用 fake 对象。
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

# ── 公共构造 ──
from config_loader import load_field, load_constraints
from state import BState
from small_model.component import SmallModelComponent

field = load_field(os.path.join(_PROJ_ROOT, "config", "field.yaml"))
constraints = load_constraints(os.path.join(_PROJ_ROOT, "config", "default_constraints.yaml"))
gc = constraints["global"]

def new_component():
    """构造全新 BState + SmallModelComponent (隔离各用例状态)。"""
    bs = BState(field, gc)
    smc = SmallModelComponent(bs)
    return bs, smc

# ── Test 1: 默认 (无 handler, phase1) land 仍生成下压 goal ──
print("\n📋 Test 1: 默认 (无 handler) land 生成 stub 下压 goal (零回归)")
bs1, smc1 = new_component()
plan1 = {"action": {"actions": [{"code": "land"}], "safety_constraints": {}}}
r1 = smc1._handle_generate_goal(plan1)
check("默认 land 返回 ok", r1.get("status") == "ok", str(r1))
check("默认 land 生成 goal", "goal" in r1, str(r1))
check("默认 land goal z ≈ floor 0.3", abs(r1["goal"]["goal"][2] - 0.3) < 1e-9,
      str(r1["goal"]["goal"]))
check("默认 land 进入目标缓存", smc1.get_current_goal() is not None)
check("默认 land 状态 executing", bs1.small_model_status == "executing",
      bs1.small_model_status)

# ── Test 2: 注入 handler (phase2) land → AUTO.LAND ──
print("\n📋 Test 2: 注入 handler land → AUTO.LAND (不生成 goal, plan 完成)")
bs2, smc2 = new_component()
events2 = []
handler_calls2 = []

def fake_sender(msg):
    events2.append(msg)

def fake_land_handler():
    handler_calls2.append(1)

smc2.set_event_sender(fake_sender)
smc2.set_land_handler(fake_land_handler)
plan2 = {"action": {"actions": [{"code": "land"}], "safety_constraints": {}}}
r2 = smc2._handle_generate_goal(plan2)
check("handler land 返回 ok", r2.get("status") == "ok", str(r2))
check("handler land note 正确", r2.get("note") == "land → AUTO.LAND", str(r2))
check("handler land 不生成 goal", "goal" not in r2, str(r2))
check("handler land 目标缓存为 None", smc2.get_current_goal() is None)
check("handler land plan 标记完成 (status idle)", bs2.small_model_status == "idle",
      bs2.small_model_status)
completed2 = [e for e in events2
              if e.get("tool") == "status"
              and e.get("payload", {}).get("flightStatus") == "completed"]
check("handler land 发 completed 事件", len(completed2) == 1,
      f"events={[e.get('tool') for e in events2]}")
check("completed 事件 currentAction/total 正确",
      completed2 and completed2[0]["payload"]["currentAction"] == 1
      and completed2[0]["payload"]["totalActions"] == 1,
      str(completed2[0]["payload"]) if completed2 else "no event")
check("handler 被调用一次", len(handler_calls2) == 1, f"calls={len(handler_calls2)}")

# ── Test 3: 非 land 动作 (takeoff) 不受 handler 影响 ──
print("\n📋 Test 3: takeoff 不受 land handler 影响")
bs3, smc3 = new_component()
handler_calls3 = []
smc3.set_land_handler(lambda: handler_calls3.append(1))
plan3 = {"action": {"actions": [{"code": "takeoff", "value": 1.0}], "safety_constraints": {}}}
r3 = smc3._handle_generate_goal(plan3)
check("takeoff 返回 ok 且生成 goal", r3.get("status") == "ok" and "goal" in r3, str(r3))
check("takeoff goal z ≈ 1.0", abs(r3["goal"]["goal"][2] - 1.0) < 1e-9,
      str(r3["goal"]["goal"]))
check("takeoff 不触发 land handler", len(handler_calls3) == 0,
      f"calls={len(handler_calls3)}")

# ── Test 4: 无 handler 时 land 在推进路径 (后置动作) 仍走 goal ──
print("\n📋 Test 4: 无 handler 推进路径 land 后置动作仍生成 goal")
bs4, smc4 = new_component()
plan4 = {"action": {"actions": [
    {"code": "goto", "target": [1.0, 1.0, 1.0]},
    {"code": "land"},
], "safety_constraints": {}}}
r4 = smc4._handle_generate_goal(plan4)
check("首条 goto 生成 goal", "goal" in r4 and r4["status"] == "ok", str(r4))
check("goto 后 index == 0", bs4.current_action_index == 0, str(bs4.current_action_index))
arrived = smc4.check_arrival_and_advance([1.0, 1.0, 1.0])
check("到达 goto 推进到 land", arrived and bs4.current_action_index == 1,
      f"arrived={arrived} index={bs4.current_action_index}")
land_goal = smc4.get_current_goal()
check("无 handler land 生成下压 goal", land_goal is not None
      and abs(land_goal["goal"][2] - 0.3) < 1e-9,
      str(land_goal))

# ── Test 5: 有 handler 推进路径命中 land → 触发 AUTO.LAND 兜底 ──
print("\n📋 Test 5: 推进路径命中 land (phase2) → handler 锁外触发")
bs5, smc5 = new_component()
events5 = []
handler_calls5 = []
smc5.set_event_sender(lambda m: events5.append(m))
smc5.set_land_handler(lambda: handler_calls5.append(1))
plan5 = {"action": {"actions": [
    {"code": "goto", "target": [1.0, 1.0, 1.0]},
    {"code": "land"},
], "safety_constraints": {}}}
r5 = smc5._handle_generate_goal(plan5)
check("首条 goto 生成 goal", "goal" in r5 and r5["status"] == "ok", str(r5))
arrived5 = smc5.check_arrival_and_advance([1.0, 1.0, 1.0])
check("推进到 land 并返回", arrived5, f"arrived={arrived5}")
check("land 后 plan 完成 (status idle)", bs5.small_model_status == "idle",
      bs5.small_model_status)
check("land 后目标缓存为 None", smc5.get_current_goal() is None)
check("推进路径 handler 触发一次", len(handler_calls5) == 1,
      f"calls={len(handler_calls5)}")
completed5 = [e for e in events5
              if e.get("tool") == "status"
              and e.get("payload", {}).get("flightStatus") == "completed"]
check("推进路径发 completed 事件", len(completed5) == 1,
      f"events={[e.get('tool') for e in events5]}")

# ── Test 6: handler 在锁外执行 (持锁检测) ──
print("\n📋 Test 6: handler 调用不发生在持锁期间 (B-6 锁纪律)")
bs6, smc6 = new_component()
lock_held = []

def probe_lock():
    """handler: 检测调用时 self._lock 是否被持有。"""
    lock_held.append(smc6._lock.locked())

smc6.set_land_handler(probe_lock)
plan6 = {"action": {"actions": [{"code": "land"}], "safety_constraints": {}}}
r6 = smc6._handle_generate_goal(plan6)
check("handler land 返回 ok", r6.get("status") == "ok", str(r6))
check("handler 被调用", len(lock_held) == 1, f"probes={lock_held}")
check("handler 调用时 self._lock 未被持有", lock_held == [False], str(lock_held))

# ── Summary ──
print(f"\n{'='*50}")
print(f"  S8.4 land 测试结果: {passed} 通过 / {passed+failed} 总数")
if failed == 0:
    print(f"  ✅ 全部通过!")
else:
    print(f"  ❌ {failed} 失败")
print(f"{'='*50}")
sys.exit(0 if failed == 0 else 1)
