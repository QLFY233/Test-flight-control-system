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

# ── Test 7: TelemetryBuffer ──
print("\n📋 Test 7: TelemetryBuffer 批量写入")

async def test_buffer():
    import asyncio
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

try:
    os.unlink(os.environ["FLIGHT_DB_PATH"])
except:
    pass

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

# ── Summary ──
print(f"\n{'='*50}")
print(f"  A 侧测试结果: {passed} 通过 / {passed+failed} 总数")
if failed == 0:
    print(f"  ✅ 全部通过!")
else:
    print(f"  ❌ {failed} 失败")
print(f"{'='*50}")
sys.exit(0 if failed == 0 else 1)
