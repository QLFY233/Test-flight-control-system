"""Async in-memory message router for component bus.

Routes bus.call() requests to registered components within backend-A.
Cross-process calls (to solver/monitor) are forwarded via the bridge.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Optional

from backend_A.bus.protocol import (
    MSG_CALL,
    MSG_EVENT,
    MSG_RESULT,
    MSG_ERROR,
    SCHEMA_VERSION,
    COMP_BETA,
    COMP_SOLVER,
    COMP_MONITOR,
    COMP_HEARTBEAT,
)
from backend_A.bus.registry import get, list_all, accepts, get_instance

logger = logging.getLogger(__name__)

# Bridge reference (set by bridge.py at startup)
_bridge: Optional[Any] = None


def set_bridge(bridge: Any) -> None:
    """Set the IPC bridge for cross-process forwarding."""
    global _bridge
    _bridge = bridge


async def call(to: str, tool: str, args: dict, call_id: Optional[str] = None) -> dict:
    """Route a call to a component.

    - If target is local (alpha/beta/analytics): call directly.
    - If target is remote (solver/monitor): forward via IPC bridge.
    """
    cid = call_id or str(uuid.uuid4())
    msg = {
        "schema_version": SCHEMA_VERSION,
        "from": "A",
        "to": to,
        "msg_type": MSG_CALL,
        "call_id": cid,
        "tool": tool,
        "args": args,
        "payload": {},
        "ts": time.time(),
    }

    # Remote targets → forward via IPC bridge
    if to in (COMP_SOLVER, COMP_MONITOR):
        if _bridge is None:
            logger.error(f"bus/router: no IPC bridge, cannot forward to '{to}'")
            return {"error": "no ipc bridge", "call_id": cid}
        try:
            await _bridge.send_call(msg)
            return {"status": "forwarded", "call_id": cid}
        except Exception as exc:
            logger.error(f"bus/router: IPC forward to '{to}' failed: {exc}")
            return {"error": str(exc), "call_id": cid}

    # Local targets
    entry = get(to)
    if entry is None:
        logger.warning(f"bus/router: unknown target '{to}', available: {list_all()}")
        return {"error": f"unknown target: {to}", "call_id": cid}

    if not accepts(to, tool):
        logger.warning(f"bus/router: component '{to}' does not accept tool '{tool}'")
        return {"error": f"tool '{tool}' not accepted by '{to}'", "call_id": cid}

    instance = get_instance(to)
    if instance is None:
        return {"error": f"no instance for '{to}'", "call_id": cid}

    # Dispatch based on component type
    try:
        if to == COMP_BETA:
            result = await instance.handle_tool_call(tool, args)
        elif hasattr(instance, "handle_call"):
            result = await instance.handle_call(tool, args, cid)
        elif hasattr(instance, "analyze"):
            result = instance.analyze(args.get("data", []), args.get("params", {}))
        else:
            result = {"error": f"component '{to}' has no dispatch method", "call_id": cid}
        return {"status": "ok", "result": result, "call_id": cid}
    except Exception as exc:
        logger.error(f"bus/router: call to '{to}.{tool}' failed: {exc}", exc_info=True)
        return {"error": str(exc), "call_id": cid}


async def emit_event(to: str, tool: str, payload: dict) -> None:
    """Emit an event into the bus for local components to handle."""
    msg = {
        "schema_version": SCHEMA_VERSION,
        "from": "A",
        "to": to,
        "msg_type": MSG_EVENT,
        "call_id": str(uuid.uuid4()),
        "tool": tool,
        "args": {},
        "payload": payload,
        "ts": time.time(),
    }
    # Dispatch to local component if registered
    instance = get_instance(to)
    if instance and hasattr(instance, "handle_event"):
        try:
            await instance.handle_event(tool, payload)
        except Exception as exc:
            logger.error(f"bus/router: event dispatch to '{to}.{tool}' failed: {exc}")

    # Also try to forward to B if applicable
    if _bridge and to in (COMP_SOLVER, COMP_MONITOR):
        try:
            await _bridge.send_event(msg)
        except Exception as exc:
            logger.error(f"bus/router: event forward to '{to}' failed: {exc}")
