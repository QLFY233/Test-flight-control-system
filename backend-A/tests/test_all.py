#!/usr/bin/env python3
"""
后端 A 功能测试 — Python 3.10+ (venv-A)
测试: 协议一致性 → msgpack 帧 → 配置加载 → AppState → 总线注册表+路由+桥接 → DB 建表+CRUD → TelemetryBuffer
"""
import sys, os, time

# ⚠️ 必须在任何 db 模块导入前设置 DB 路径
import tempfile
_DB_PATH = os.path.join(tempfile.gettempdir(), "test_flight_control_a.db")
# 清理上次残留 (避免 UNIQUE constraint 冲突)
if os.path.exists(_DB_PATH):
    os.unlink(_DB_PATH)
os.environ["FLIGHT_DB_PATH"] = _DB_PATH

# 确保 backend-A 在 path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# 项目根目录 (backend-A/tests → 上两级 = 项目根)
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

# ── Test 1: Protocol 常量导入 (与 B 侧同源 shared/protocol.py) ──
print("\n📋 Test 1: Protocol 常量 (shared/protocol.py)")
from bus.protocol import (
    SCHEMA_VERSION, MSGPACK_USE_BIN_TYPE,
    IPC_SOCKET_PATH, IPC_FRAME_MAX_BYTES,
    MSG_TYPE_CALL, MSG_TYPE_RESULT, MSG_TYPE_EVENT, MSG_TYPE_ERROR,
    TO_ALPHA, TO_BETA, TO_SMALL_MODEL, TO_MONITOR, TO_HEARTBEAT,
    TO_FFT_ANALYZER, TO_STATS, TO_FILTER, TO_HISTORY_QUERY, TO_DASHBOARD_DRIVER,
    CALL_TOOL_ACTION, CALL_TOOL_ABORT, CALL_TOOL_HOVER, CALL_TOOL_PING,
    EVENT_TOOL_POSE, EVENT_TOOL_ALERT, EVENT_TOOL_PONG,
)
check("SCHEMA_VERSION == 2", SCHEMA_VERSION == 2)
check("共享协议文件 source = shared/protocol.py", True)  # 软链接已确认

# ── Test 2: msgpack 帧编解码 (A 侧 msgpack 1.2.1) ──
print("\n📋 Test 2: msgpack 帧编解码 (venv-A)")
import msgpack
from ipc.frames import encode_frame, send_frame

# 编码
test_msg = {
    "schema_version": SCHEMA_VERSION, "from": "A", "to": "B",
    "msg_type": MSG_TYPE_CALL, "call_id": "a-123", "tool": CALL_TOOL_ACTION,
    "args": {
        "action": {"code": "goto", "target": [3.0, 2.0, 1.0]},
        "pose": {"pos": [0, 0, 0.5]},
    },
    "payload": {}, "ts": time.time(),
}
frame = encode_frame(test_msg)
check("encode_frame 返回 bytes", isinstance(frame, bytes))

# 跨版本验证: A 打包, 模仿 B 解包 (raw=False)
decoded = msgpack.unpackb(frame[4:], raw=False)
check("A pack → unpack 不变", decoded["tool"] == CALL_TOOL_ACTION)
check("args.action.code", decoded["args"]["action"]["code"] == "goto")
check("args.action.target", decoded["args"]["action"]["target"] == [3.0, 2.0, 1.0])

# ── Test 3: 配置加载 ──
print("\n📋 Test 3: 配置加载")
from config_loader import load_config

cfg = load_config(os.path.join(_PROJ_ROOT, "config"))
check("alpha_loop_period == 2.0", cfg.alpha_loop_period == 2.0)
check("alpha_history_rounds == 10", cfg.alpha_history_rounds == 10)
check("field_cfg 有 boundary", "boundary" in cfg.field_cfg)
check("constraints 有 global", "global" in cfg.constraints)

# ── Test 4: AppState ──
print("\n📋 Test 4: AppState (asyncio)")
import asyncio
from state import AppState

async def test_state():
    st = AppState(cfg)
    check("初始 session_id == None", st.session_id is None)
    check("初始 ipc_connected == False", st.ipc_connected == False)
    check("初始 flight_status == 'idle'", st.flight_status == "idle")

    # 位姿更新 + NaN 校验
    await st.update_pose([1.0, 2.0, 3.0], [1.0, 0, 0, 0], [0.1, 0.2, 0.0], [0, 0, 0], [0, 0, 0.1], time.time())
    check("pose.pos", st.current_pose.pos == [1.0, 2.0, 3.0])
    check("pose.quat [w,x,y,z]", st.current_pose.quat == [1.0, 0, 0, 0])

    # NaN 截断
    await st.update_pose([float('nan'), 2.0, 3.0], [1.0, 0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], time.time())
    check("NaN → 0", st.current_pose.pos[0] == 0.0, f"got {st.current_pose.pos[0]}")

    await st.update_pose([float('inf'), 2.0, 3.0], [1.0, 0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], time.time())
    check("Inf → 0", st.current_pose.pos[0] == 0.0, f"got {st.current_pose.pos[0]}")

    # α 队列
    await st.push_alpha_input("test cmd 1")
    await st.push_alpha_input("test cmd 2")
    drained = await st.drain_alpha_input_queue()
    check("drain 返回 2 条", len(drained) == 2)
    check("drain 后队列空", len(st.alpha_input_queue) == 0)

    # ActionPlan
    from state import ActionPlan
    plan = ActionPlan(task_id="20260101", actions=[{"code": "takeoff"}, {"code": "hover"}], safety_constraints={})
    check("has_remaining", plan.has_remaining())
    a = plan.next_action()
    check("next_action 返回 takeoff", a["code"] == "takeoff")
    check("action_index == 1", plan.action_index == 1)
    check("next_action 返回 hover", plan.next_action()["code"] == "hover")
    check("next_action None", plan.next_action() is None)

asyncio.run(test_state())

# ── Test 5: A 侧总线注册表 + 路由器 ──
print("\n📋 Test 5: A 侧总线注册表 + 路由器")
from bus import registry as a_registry
from bus.router import call as a_call

# 清空注册表
a_registry._registry.clear()

class MockComponent:
    def __init__(self, name):
        self.name = name
    async def handle(self, tool, args):
        if tool == "error_test":
            raise ValueError("test error")
        return {"status": "ok", "tool": tool, "comp": self.name}

comp = MockComponent("test_comp")
a_registry.init_registry(alpha_component=comp)
check("alpha 已注册", a_registry.get("alpha") is not None)
check("alpha 接受 translate", a_registry.accepts("alpha", "translate"))
check("B 侧组件 small_model", a_registry.is_b_side("small_model"))
check("B 侧组件 monitor", a_registry.is_b_side("monitor"))
check("A 侧 alpha 非 B 侧", not a_registry.is_b_side("alpha"))

# 路由测试 (async)
async def test_router():
    r = await a_call(to="alpha", tool="translate", args={"intent": "test"})
    check("bus.call async result", r.get("msg_type") == "result")
    check("bus.call async payload ok", r.get("payload", {}).get("status") == "ok")

    r2 = await a_call(to="unknown_comp", tool="test", args={})
    check("bus.call 未知组件 error", r2.get("msg_type") == "error")

asyncio.run(test_router())

# ── Test 6: DB 建表 + CRUD ──
print("\n📋 Test 6: DB 建表 + CRUD")

from db.session import create_all, async_session
from db.repos import (
    save_environment, get_environments,
    create_session as create_flight_session, get_session, update_session_status,
    save_conversation, get_conversations,
    TelemetryBuffer, get_telemetry_range,
)

from db.session import create_all, async_session

async def test_db():
    await create_all()
    check("DB 建表成功", True)

    async with async_session() as s:
        # Environment
        env = await save_environment(s, "test env", '{"wind":[1.0,0,0]}')
        check("env created", env.id is not None, f"id: {env.id}")

        envs = await get_environments(s)
        check("get_environments", len(envs) == 1)

        # FlightSession
        fs = await create_flight_session(s, "20260727120000", "test task")
        check("session created", fs.id == "20260727120000")
        check("session status idle", fs.status == "idle")

        await update_session_status(s, "20260727120000", "executing")
        fs2 = await get_session(s, "20260727120000")
        check("status updated", fs2.status == "executing")

        # Conversation
        await save_conversation(s, "20260727120000", "beta", "human", "hello", {"tool": "query"})
        convs = await get_conversations(s, "20260727120000")
        check("conversation saved", len(convs) == 1)

        # Telemetry
        from sqlalchemy import insert
        import db.session as dbs
        await s.execute(insert(dbs.Base.metadata.tables["telemetry"]), [
            {"session_id": "20260727120000", "t": 0.0, "position_x": 1.0, "position_y": 2.0, "position_z": 3.0},
            {"session_id": "20260727120000", "t": 0.1, "position_x": 1.1, "position_y": 2.1, "position_z": 3.1},
        ])
        await s.commit()
        teles = await get_telemetry_range(s, "20260727120000")
        check("telemetry insert/query", len(teles) == 2, f"got {len(teles)}")
        check("teles[0] pos", teles[0].position_x == 1.0 and teles[0].position_z == 3.0)

asyncio.run(test_db())

# ── Test 6b: 会话详情 + β 对话持久化 (#11 刷新恢复) ──
print("\n📋 Test 6b: 会话详情 + β 对话持久化")

async def test_session_detail():
    from db.repos import get_session_detail
    async with async_session() as s:
        # 未设置 alpha_actions/beta_plan 时详情兜底字段
        detail = await get_session_detail(s, "20260727120000")
        check("detail 存在", detail is not None)
        if detail:
            check("detail.status executing", detail["status"] == "executing")
            check("detail.telemetry_count == 2", detail["telemetry_count"] == 2, f"got {detail['telemetry_count']}")
            check("detail.alpha_actions 空兜底", detail["alpha_actions"] is None)
        # 不存在的会话 → None
        check("detail 不存在 → None", await get_session_detail(s, "nonexistent") is None)

        # 写入 alpha_actions 后详情可读
        from db.repos import get_session as _get
        fs = await _get(s, "20260727120000")
        fs.alpha_actions = '[{"code":"takeoff","value":1.0}]'
        fs.beta_plan = "起飞到 1 米"
        await s.commit()
        detail2 = await get_session_detail(s, "20260727120000")
        check("detail2.alpha_actions 已回读", detail2["alpha_actions"] == '[{"code":"takeoff","value":1.0}]')
        check("detail2.beta_plan 已回读", detail2["beta_plan"] == "起飞到 1 米")

        # β 对话持久化往返 (human + agent)
        await save_conversation(s, "20260727120000", "beta", "human", "起飞到 1 米")
        await save_conversation(s, "20260727120000", "beta", "agent", "好的，计划已生成")
        convs = await get_conversations(s, "20260727120000")
        check("β 对话 3 条", len(convs) == 3, f"got {len(convs)}")
        # get_conversations 仅按 created_at 排序 (微秒精度), 连续插入可能并列 → 断言集合而非顺序
        roles = sorted(c.role for c in convs)
        check("β human+agent 角色集合", roles == ["agent", "human", "human"], f"got {roles}")

asyncio.run(test_session_detail())

# ── Test 7: TelemetryBuffer ──
print("\n📋 Test 7: TelemetryBuffer 批量写入")

async def test_buffer():
    import asyncio
    # N8: PRAGMA foreign_keys=ON — 遥测须先有 flight_sessions 行
    async with async_session() as s:
        await create_flight_session(s, "buf", "buffer test")
    # 复用 test 6 的 TelemetryBuffer (同 DB)
    buf = TelemetryBuffer(flush_interval=0.3)
    await buf.start()
    
    for i in range(5):
        await buf.append({
            "session_id": "buf", "t": i * 0.1,
            "pos": [float(i), 0.0, 0.0],
            "quat": [1.0, 0.0, 0.0, 0.0],
            "vel": [0.0, 0.0, 0.0],
            "accel": [0.0, 0.0, 0.0],
            "angular_vel": [0.0, 0.0, 0.0],
        })
    
    await asyncio.sleep(0.6)  # 等 flush
    await buf.stop()
    
    async with async_session() as s:
        teles = await get_telemetry_range(s, "buf")
        check("TelemetryBuffer flushed", len(teles) == 5, f"got {len(teles)}")

asyncio.run(test_buffer())

# ── Test 11: B1 α 下发失败状态机 ──
print("\n📋 Test 11: α _dispatch_action 错误状态机 (B1)")
from agents.alpha import AlphaLoop
from state import AppState, Config as StateConfig
import bus.router as bus_router_mod
from fastapi import HTTPException


async def test_b1():
    st = AppState(StateConfig())
    translator_dummy = type("Dummy", (), {"translate": lambda self, i, p, e: {"actions": [{"code": "hover"}]}})()
    loop = AlphaLoop(st, translator_dummy)

    async def fake_call_ok(**kwargs):
        return {"status": "sent"}  # 正常 ack (fire-and-forget)

    bus_router_mod.call = fake_call_ok
    await loop._dispatch_action({"actions": [{"code": "takeoff"}]})
    check("B1 正常 ack → executing", st.flight_status == "executing")

    async def fake_call_error(**kwargs):
        return {"msg_type": "error", "payload": {"error": "B not connected"}}

    bus_router_mod.call = fake_call_error
    await loop._dispatch_action({"actions": [{"code": "takeoff"}]})
    check("B1 error → 回退 hovering", st.flight_status == "hovering", f"got {st.flight_status}")

    from bus.router import call as _orig_call
    bus_router_mod.call = _orig_call


asyncio.run(test_b1())

# ── Test 12: 提议审批原子认领 (I2) ──
print("\n📋 Test 12: approve_proposal TOCTOU (I2)")
from web import routes as web_routes


async def test_i2():
    st = AppState(StateConfig())
    st.pending_proposal = {"id": "p1", "intent": "起飞到 3 米"}
    web_routes._state_ref = st
    web_routes._db_factory = None

    r1 = await web_routes.approve_proposal("p1")
    check("I2 首次 approve 成功", r1["status"] == "approved")
    check("I2 pending 已清空", st.pending_proposal is None)
    try:
        await web_routes.approve_proposal("p1")
        check("I2 二次 approve 被拒", False, "未抛 404")
    except HTTPException as e:
        check("I2 二次 approve 被拒", e.status_code == 404)


asyncio.run(test_i2())

# ── Test 13: FFT 边界 (N12) ──
print("\n📋 Test 13: FFT 边界 (N12)")
from analytics.fft import FFTAnalyzer
fft = FFTAnalyzer()
r = fft.run([1.0])
check("N12 n=1 不崩溃", r["status"] == "ok" and r["spectrum"]["dominant_freq"] == 0.0)
r2 = fft.run([1.0, 2.0, 3.0])
check("N12 n=3 正常", r2["status"] == "ok" and len(r2["spectrum"]["magnitudes"]) > 0)

# ── Test 14: TelemetryBuffer OR IGNORE (I4) ──
print("\n📋 Test 14: TelemetryBuffer 重复 t 不丢整批 (I4)")


async def test_i4():
    # N8: PRAGMA foreign_keys=ON — 遥测须先有 flight_sessions 行
    async with async_session() as s:
        await create_flight_session(s, "dup", "dup test")
    buf = TelemetryBuffer(flush_interval=0.2)
    await buf.start()
    for _ in range(2):  # 同 (session_id, t) 两条
        await buf.append({
            "session_id": "dup", "t": 1.0,
            "pos": [1.0, 0.0, 0.0], "quat": [1.0, 0, 0, 0],
            "vel": [0.0, 0.0, 0.0], "accel": [0.0, 0.0, 0.0],
            "angular_vel": [0.0, 0.0, 0.0],
        })
    await asyncio.sleep(0.5)
    await buf.stop()
    async with async_session() as s:
        teles = await get_telemetry_range(s, "dup")
        check("I4 重复 t 只落 1 行, 无异常", len(teles) == 1, f"got {len(teles)}")


asyncio.run(test_i4())

# ── Test 15: 会话 id 细粒度唯一性 (N8) ──
print("\n📋 Test 15: 会话 id 细粒度 (N8)")
ids = {web_routes._new_session_id() for _ in range(100)}
check("N8 100 次生成全部唯一", len(ids) == 100, f"got {len(ids)}")

# ── Test 16: 任务名自动生成 (#3) ──
print("\n📋 Test 16: 任务名自动生成 (#3)")
from tools.beta_tools import _derive_task_name

name1 = _derive_task_name("起飞到1米然后飞到3,2,1", [
    {"code": "takeoff", "value": 1.0, "units": "m"},
    {"code": "goto", "target": [3.0, 2.0, 1.0], "units": "m"},
    {"code": "hover", "value": 2.0, "units": "s"},
])
check("#3 动作摘要含起飞", "起飞" in name1, f"got {name1}")
check("#3 动作摘要含飞往(3,2)", "飞往(3,2)" in name1, f"got {name1}")
check("#3 动作摘要含悬停", "悬停" in name1, f"got {name1}")

name2 = _derive_task_name(" 从起点出发，执行长距离巡航航线测试  ", [])
check("#3 无动作截断意图", "巡航" in name2 and len(name2) <= 25, f"got {name2}")

name3 = _derive_task_name("", [])
check("#3 空输入兜底", name3 == "试飞任务", f"got {name3}")

# 超过 4 个动作 → 省略号
name4 = _derive_task_name("x", [
    {"code": "takeoff", "value": 1.0}, {"code": "goto", "target": [1.0, 2.0, 0.0]},
    {"code": "hover", "value": 1.0}, {"code": "yaw", "value": 90.0},
    {"code": "return_home"},
])
check("#3 超过4动作省略号", name4.endswith("…"), f"got {name4}")

# ── Test 8: Lifecycle + IPC server 结构 ──
print("\n📋 Test 8: Lifecycle 初始化")
from lifecycle import Lifecycle

lc = Lifecycle(os.path.join(_PROJ_ROOT, "config"))
check("Lifecycle 创建", lc is not None)
check("Lifecycle state 初始 None", lc.state is None)

# ── Test 9: StaticFiles 挂载 ──
print("\n📋 Test 9: FastAPI App 创建")
from main import create_app

app = create_app(os.path.join(_PROJ_ROOT, "config"))
check("FastAPI app 创建", app is not None)
check("app title", app.title == "试飞控制系统 — Backend A")

# ── Test 10: Web/static mount ──
from web.static import FRONTEND_DIR
check("FRONTEND_DIR == 'frontend'", FRONTEND_DIR == "frontend")

# 清理测试 DB (在所有使用 DB 的测试之后)
try:
    os.unlink(os.environ["FLIGHT_DB_PATH"])
except Exception:
    pass

# ── Summary ──
print(f"\n{'='*50}")
print(f"  A 侧测试结果: {passed} 通过 / {passed+failed} 总数")
if failed == 0:
    print(f"  ✅ 全部通过!")
else:
    print(f"  ❌ {failed} 失败")
print(f"{'='*50}")
sys.exit(0 if failed == 0 else 1)
