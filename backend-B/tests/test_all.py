#!/usr/bin/env python3
"""
后端 B 功能测试 — Python 3.8 + ROS Noetic (venv-B)
测试: 协议常量 → msgpack 帧编解码 → 配置加载 → 状态管理 → 总线注册表 → IPC 帧
"""
import sys, os, struct, time

# 确保 backend-B 在 path 中
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

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

# ── Test 1: Protocol 常量导入 ──
print("\n📋 Test 1: Protocol 常量导入")
from bus.protocol import (
    SCHEMA_VERSION, MSGPACK_USE_BIN_TYPE,
    IPC_SOCKET_PATH, IPC_FRAME_MAX_BYTES,
    IPC_PING_INTERVAL, IPC_PONG_TIMEOUT, IPC_RECONNECT_INTERVAL,
    MSG_TYPE_CALL, MSG_TYPE_RESULT, MSG_TYPE_EVENT, MSG_TYPE_ERROR,
    TO_SMALL_MODEL, TO_MONITOR, TO_HEARTBEAT,
    CALL_TOOL_ACTION, CALL_TOOL_ABORT, CALL_TOOL_HOVER, CALL_TOOL_PING,
    EVENT_TOOL_POSE, EVENT_TOOL_TELEMETRY, EVENT_TOOL_STATUS, EVENT_TOOL_REJECT,
    EVENT_TOOL_PONG, EVENT_TOOL_ALERT,
    ACTION_CODE_TAKEOFF, ACTION_CODE_LAND, ACTION_CODE_GOTO,
    ACTION_CODE_HOVER, ACTION_CODE_RETURN_HOME,
    FLIGHT_STATUS_IDLE, FLIGHT_STATUS_EXECUTING, FLIGHT_STATUS_ABORTED,
    MODE_MANUAL, MODE_AUTO,
    ALERT_LEVEL_WARNING, ALERT_LEVEL_CRITICAL,
    REJECT_UNKNOWN_ACTION_CODE,
)
check("SCHEMA_VERSION == 2", SCHEMA_VERSION == 2, f"got {SCHEMA_VERSION}")
check("MSGPACK_USE_BIN_TYPE == True", MSGPACK_USE_BIN_TYPE == True)
check("IPC_SOCKET_PATH", IPC_SOCKET_PATH == "/tmp/flight_control_AB.sock")
check("IPC_FRAME_MAX_BYTES == 16MiB", IPC_FRAME_MAX_BYTES == 16 * 1024 * 1024)
check("MSG_TYPE_CALL == 'call'", MSG_TYPE_CALL == "call")
check("TO_SMALL_MODEL == 'small_model'", TO_SMALL_MODEL == "small_model")
check("CALL_TOOL_ACTION == 'action'", CALL_TOOL_ACTION == "action")
check("EVENT_TOOL_POSE == 'pose'", EVENT_TOOL_POSE == "pose")
check("ACTION_CODE_TAKEOFF == 'takeoff'", ACTION_CODE_TAKEOFF == "takeoff")
check("FLIGHT_STATUS_IDLE == 'idle'", FLIGHT_STATUS_IDLE == "idle")
check("MODE_MANUAL == 'manual'", MODE_MANUAL == "manual")
check("9 个动作编码完整", len({ACTION_CODE_TAKEOFF, ACTION_CODE_LAND, ACTION_CODE_GOTO, "move", "climb", "descend", "yaw", ACTION_CODE_HOVER, ACTION_CODE_RETURN_HOME}) == 9)

# ── Test 2: msgpack 帧编解码 ──
print("\n📋 Test 2: msgpack 长度前缀帧编解码")
import msgpack
from bus.protocol import MSGPACK_USE_BIN_TYPE, IPC_FRAME_MAX_BYTES
from ipc.frames import encode_frame, recv_frame, send_frame

# 编码测试
test_msg = {
    "schema_version": SCHEMA_VERSION,
    "from": "B", "to": "A",
    "msg_type": MSG_TYPE_EVENT,
    "call_id": "", "tool": EVENT_TOOL_POSE,
    "args": {}, "payload": {"pos": [1.0, 2.0, 3.0]}, "ts": time.time(),
}
frame = encode_frame(test_msg)
check("encode_frame 返回 bytes", isinstance(frame, bytes), f"type: {type(frame)}")
check("长度前缀正确 (4字节大端)", struct.unpack(">I", frame[:4])[0] == len(frame) - 4)

# 解码测试 (用 socket 模拟)
import socket
sockets = socket.socketpair()

try:
    # B 侧发送
    send_frame(sockets[0], test_msg)
    
    # A 侧接收 (模拟跨进程)
    decoded = recv_frame(sockets[1])
    check("recv_frame 成功", isinstance(decoded, dict))
    check("schema_version 不变", decoded.get("schema_version") == SCHEMA_VERSION)
    check("payload.pos 正确", decoded.get("payload", {}).get("pos") == [1.0, 2.0, 3.0])
    check("ts 接近", abs(decoded.get("ts", 0) - test_msg["ts"]) < 0.001)
finally:
    sockets[0].close()
    sockets[1].close()

# 帧过大抛出异常
big_msg = {"data": "x" * (IPC_FRAME_MAX_BYTES + 100)}
try:
    encode_frame(big_msg)
    check("帧过大应抛 ValueError", False, "no exception")
except ValueError:
    check("帧过大抛出 ValueError", True)

# use_bin_type 一致性
b_data = msgpack.packb(b"hello", use_bin_type=True)
decoded_b = msgpack.unpackb(b_data, raw=False)
check("msgpack use_bin_type 一致 (bytes roundtrip)", decoded_b == b"hello")

s_data = msgpack.packb("hello", use_bin_type=True)
decoded_s = msgpack.unpackb(s_data, raw=False)
check("msgpack use_bin_type 一致 (str roundtrip)", decoded_s == "hello")

# ── Test 3: 配置加载 ──
print("\n📋 Test 3: 配置加载")
from config_loader import load_field, load_constraints

field = load_field("../config/field.yaml")
check("field.yaml 有 boundary", "boundary" in field)
check("boundary.x == [0,5]", field["boundary"]["x"] == [0.0, 5.0])
check("boundary.y == [0,4]", field["boundary"]["y"] == [0.0, 4.0])
check("boundary.z == [0,3]", field["boundary"]["z"] == [0.0, 3.0])
check("field.yaml 有 home", "home" in field)
check("home.position == [0,0,0.5]", field["home"]["position"] == [0.0, 0.0, 0.5])

constraints = load_constraints("../config/default_constraints.yaml")
check("constraints 有 global", "global" in constraints)
check("speed_max == 1.5", constraints["global"]["speed_max"] == 1.5)
check("ceiling == 2.5", constraints["global"]["ceiling"] == 2.5)
check("floor == 0.3", constraints["global"]["floor"] == 0.3)
check("有 presets", "presets" in constraints)

# ── Test 4: BState 状态管理 ──
print("\n📋 Test 4: BState 状态管理")
from state import BState

bs = BState(field, constraints["global"])
check("BState 初始化 field", bs.field is field)
check("BState 初始化 constraints", bs.default_constraints is constraints["global"])
check("初始 ipc_connected == False", bs.ipc_connected == False)
check("初始 small_model_status == 'idle'", bs.small_model_status == "idle")

# 位姿更新
bs.update_pose([1.0, 2.0, 3.0], [1.0, 0.0, 0.0, 0.0], [0.1, 0.2, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.1], time.time())
check("pose.pos 正确", bs.current_pose.pos == [1.0, 2.0, 3.0])
check("pose.quat 正确 [w,x,y,z]", bs.current_pose.quat == [1.0, 0.0, 0.0, 0.0])
check("last_data_ts > 0", bs.last_data_ts > 0)

# ── Test 5: B 内总线注册表 + 路由器 ──
print("\n📋 Test 5: B 侧总线注册表 + 路由器")
from bus import registry as b_registry
from bus.router import call as b_call

# 清空注册表
b_registry._registry.clear()

class MockComponent:
    def __init__(self):
        self.calls = []
    def handle(self, tool, args):
        self.calls.append((tool, args))
        if tool == "error_test":
            raise ValueError("test error")
        return {"status": "ok", "tool": tool}

sm = MockComponent()
mon = MockComponent()
b_registry.init_registry(sm, mon)

check("small_model 已注册", b_registry.get(TO_SMALL_MODEL) is not None)
check("small_model 接受 generate_goal", b_registry.accepts(TO_SMALL_MODEL, "generate_goal"))
check("small_model 接受 abort", b_registry.accepts(TO_SMALL_MODEL, "abort"))
check("small_model 接受 hover", b_registry.accepts(TO_SMALL_MODEL, "hover"))
check("small_model 不接受 fft", not b_registry.accepts(TO_SMALL_MODEL, "fft"))
check("monitor 已注册", b_registry.get(TO_MONITOR) is not None)

# 路由测试
r = b_call(to=TO_SMALL_MODEL, tool="generate_goal", args={"action": "test"})
check("bus.call 返回 result", r.get("msg_type") == "result")
check("bus.call 返回 ok", r.get("payload", {}).get("status") == "ok")
check("bus.call 带 call_id", len(r.get("call_id", "")) > 0)

r2 = b_call(to=TO_SMALL_MODEL, tool="error_test", args={})
check("bus.call 组件异常返回 error", r2.get("msg_type") == "error")

r3 = b_call(to="nonexistent", tool="test", args={})
check("bus.call 未注册组件返回 error", r3.get("msg_type") == "error")
check("bus.call 未注册 error detail 含 'not registered'", "not registered" in r3.get("payload", {}).get("error", ""))

r4 = b_call(to=TO_SMALL_MODEL, tool="unknown_tool", args={})
check("bus.call 不接受 tool 返回 error", r4.get("msg_type") == "error")

# ── Test 6: IPC 帧边界测试 ──
print("\n📋 Test 6: IPC 帧边界测试")

# 模拟 B→A 消息 (pose/telemetry/status/reject/alert/pong)
event_types = [
    ("pose", {"pos": [1.5, 2.0, 0.8], "quat": [1, 0, 0, 0]}),
    ("telemetry", {"vel": [0.2, 0.0, 0.0]}),
    ("status", {"flightStatus": "executing", "currentAction": 1, "totalActions": 3}),
    ("reject", {"reason": "unknown_action_code", "actionIndex": 2}),
    ("alert", {"level": "warning", "code": "overspeed", "detail": "speed 2.1 > 1.5"}),
    ("pong", {}),
]
for tool, payload in event_types:
    evt = {"schema_version": 2, "from": "B", "to": "A", "msg_type": "event", "call_id": "", "tool": tool, "args": {}, "payload": payload, "ts": time.time()}
    frame = encode_frame(evt)
    check(f"编码 {tool} 帧成功", len(frame) > 4)

# ── Summary ──
print(f"\n{'='*50}")
print(f"  B 侧测试结果: {passed} 通过 / {passed+failed} 总数")
if failed == 0:
    print(f"  ✅ 全部通过!")
else:
    print(f"  ❌ {failed} 失败")
print(f"{'='*50}")
sys.exit(0 if failed == 0 else 1)
