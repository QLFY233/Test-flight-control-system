"""
A 内内存总线路由器 — async call 分发。
bus.call(to, tool, args) → 查注册表 → 调组件 (A 内 or B 侧桥接)。
"""
import time
import asyncio
import logging

from bus.protocol import SCHEMA_VERSION, MSG_TYPE_RESULT, MSG_TYPE_ERROR
from bus import registry

logger = logging.getLogger(__name__)


async def call(to: str, tool: str, args: dict, _from: str = "A", call_id: str = "") -> dict:
    """
    async 调用组件。若 to 在 B 侧, 经 bridge 转发。
    返回: {schema_version, from, to, msg_type, call_id, tool, payload, ts}
    """
    if not call_id:
        call_id = f"a-{time.time_ns()}"

    # B 侧组件 → IPC bridge
    if registry.is_b_side(to):
        from bus.bridge import forward_to_b
        try:
            result = await forward_to_b(to, tool, args, _from, call_id)
            return result
        except Exception as exc:
            logger.error(f"[router] bridge call to {to}.{tool} failed: {exc}")
            return _error(call_id, to, str(exc))

    # A 内组件
    entry = registry.get(to)
    if not entry:
        return _error(call_id, to, f"component '{to}' not registered")

    if not registry.accepts(to, tool):
        return _error(call_id, to, f"component '{to}' does not accept tool '{tool}'")

    component = entry["component"]
    try:
        if asyncio.iscoroutinefunction(component.handle):
            result = await component.handle(tool, args)
        else:
            result = component.handle(tool, args)
    except Exception as exc:
        logger.error(f"[router] component {to}.{tool} error: {exc}")
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
        "from": "A",
        "to": to,
        "msg_type": MSG_TYPE_ERROR,
        "call_id": call_id,
        "tool": "",
        "payload": {"error": detail},
        "ts": time.time(),
    }
