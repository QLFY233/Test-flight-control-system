"""
B 内内存总线路由器 — 同步 call 分发。
bus.call(to, tool, args) → 查注册表 → 同步调用组件 → 返回 result。
"""
import time
from bus.protocol import SCHEMA_VERSION, MSG_TYPE_CALL, MSG_TYPE_RESULT, MSG_TYPE_ERROR
from bus import registry


def call(to: str, tool: str, args: dict, _from: str = "B") -> dict:
    """
    同步调用 B 侧组件。
    返回: {schema_version, from, to, msg_type, call_id, tool, payload, ts}
    """
    call_id = f"b-{time.time_ns()}"

    entry = registry.get(to)
    if not entry:
        return _error(call_id, to, f"component '{to}' not registered")

    if not registry.accepts(to, tool):
        return _error(call_id, to, f"component '{to}' does not accept tool '{tool}'")

    component = entry["component"]
    try:
        result = component.handle(tool, args)
    except Exception as exc:
        return _error(call_id, to, str(exc))

    return {
        "schema_version": SCHEMA_VERSION,
        "from": _from,
        "to": to,
        "msg_type": MSG_TYPE_RESULT,
        "call_id": call_id,
        "tool": tool,
        "payload": result if result is not None else {},
        "ts": time.time(),
    }


def _error(call_id: str, to: str, detail: str) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "from": "B",
        "to": to,
        "msg_type": MSG_TYPE_ERROR,
        "call_id": call_id,
        "tool": "",
        "payload": {"error": detail},
        "ts": time.time(),
    }
