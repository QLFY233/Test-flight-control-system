"""
Message router for Backend B bus.

Routes incoming IPC messages to registered bus components
based on tool name or event type.
"""

import logging
from typing import Any

from backend_B.bus.protocol import (
    MSG_CALL,
    MSG_RESULT,
    MSG_EVENT,
    MSG_ERROR,
    COMP_SOLVER,
    COMP_MONITOR,
    COMP_HEARTBEAT,
)

logger = logging.getLogger("backend_b.router")


def route(msg: dict, bstate: Any, registry_getter=None) -> dict | None:
    """
    Route a decoded IPC message to the appropriate component.

    Args:
        msg: Decoded msgpack message dict with keys:
            - "type": "call" | "result" | "event" | "error"
            - "tool" (for calls): tool name
            - "args" (for calls): call arguments
            - "id" (for calls): correlation id
            - "event" (for events): event name
            - "data" (for events): event payload
        bstate: BState instance for state access
        registry_getter: Callable to resolve component names (defaults to registry.get)

    Returns:
        Response dict for calls, or None for events/errors.
    """
    if registry_getter is None:
        from backend_B.bus.registry import get as _get
        registry_getter = _get

    msg_type = msg.get("type", "")

    if msg_type == MSG_CALL:
        return _route_call(msg, bstate, registry_getter)
    elif msg_type == MSG_RESULT:
        logger.debug("Received result message (unexpected on B side): %s", msg)
        return None
    elif msg_type == MSG_EVENT:
        _route_event(msg, bstate, registry_getter)
        return None
    elif msg_type == MSG_ERROR:
        logger.warning("Received error message: %s", msg)
        return None
    else:
        logger.warning("Unknown message type: %s", msg_type)
        return None


def _route_call(msg: dict, bstate: Any, registry_getter) -> dict | None:
    """Route a 'call' message to the appropriate component."""
    tool = msg.get("tool", "")
    args = msg.get("args", {})
    call_id = msg.get("id", 0)

    logger.info("Routing call: tool=%s id=%s", tool, call_id)

    # Map tool to component
    component = _component_for_tool(tool, registry_getter)

    if component is None:
        logger.warning("No component registered for tool: %s", tool)
        return {
            "type": MSG_ERROR,
            "id": call_id,
            "error": f"No component for tool: {tool}",
        }

    handler = getattr(component, "handle", None)
    if handler is None:
        logger.warning("Component %s has no 'handle' method", component)
        return {
            "type": MSG_ERROR,
            "id": call_id,
            "error": "Component has no handle method",
        }

    try:
        result = handler(tool, args, bstate)
        return {
            "type": MSG_RESULT,
            "id": call_id,
            "tool": tool,
            "result": result,
        }
    except Exception as exc:
        logger.exception("Error handling call %s(%s): %s", tool, args, exc)
        return {
            "type": MSG_ERROR,
            "id": call_id,
            "tool": tool,
            "error": str(exc),
        }


def _route_event(msg: dict, bstate: Any, registry_getter) -> None:
    """Route an 'event' message (typically outgoing to A, but handle incoming too)."""
    event = msg.get("event", "")
    data = msg.get("data", {})

    logger.debug("Routing event: event=%s", event)

    # Events like 'pose', 'telemetry', 'alert', 'status' may come from A
    # For now, log and potentially notify monitor
    if event == "telemetry":
        bstate.last_data_ts = data.get("timestamp", bstate.last_data_ts)
    elif event == "status":
        logger.info("Status event: %s", data)
    else:
        logger.debug("Unhandled event: %s", event)


def _component_for_tool(tool: str, registry_getter) -> Any:
    """Map a tool name to the responsible bus component."""
    # Solver handles trajectory, abort, hover commands
    solver_tools = {"trajectory", "abort", "hover"}

    if tool in solver_tools:
        return registry_getter(COMP_SOLVER)

    # Ping goes to heartbeat
    if tool == "ping":
        return registry_getter(COMP_HEARTBEAT)

    # Monitor handles status queries
    if tool == "status":
        return registry_getter(COMP_MONITOR)

    # Try to route by component name
    return None
