"""A↔B IPC bridge — routes messages between A's internal bus and B's process.

When A component calls solver/monitor → forward via IPC to B.
When B sends events → route to A components.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from backend_A.bus.registry import get_instance
from backend_A.bus.protocol import (
    COMP_ALPHA,
    COMP_BETA,
    COMP_HEARTBEAT,
    MSG_EVENT,
    TOOL_ALERT,
    TOOL_PONG,
)

logger = logging.getLogger(__name__)


class Bridge:
    """Bridges A's internal bus with B's process over IPC."""

    def __init__(self) -> None:
        self._ipc_writer: Optional[asyncio.StreamWriter] = None
        self._send_lock = asyncio.Lock()
        self._app_state: Optional[Any] = None
        self._monitor_trigger: Optional[Any] = None

    def set_app_state(self, app_state: Any) -> None:
        self._app_state = app_state

    def set_monitor_trigger(self, trigger: Any) -> None:
        self._monitor_trigger = trigger

    def set_writer(self, writer: asyncio.StreamWriter) -> None:
        self._ipc_writer = writer

    def clear_writer(self) -> None:
        self._ipc_writer = None

    @property
    def is_connected(self) -> bool:
        return self._ipc_writer is not None

    async def send_call(self, msg: dict) -> None:
        """Send a call message to B via IPC."""
        if self._ipc_writer is None:
            raise RuntimeError("IPC not connected to B")
        async with self._send_lock:
            # delegate to ipc/frames send_frame
            from backend_A.ipc.frames import send_frame
            await send_frame(self._ipc_writer, msg)

    async def send_event(self, msg: dict) -> None:
        """Send an event message to B via IPC."""
        if self._ipc_writer is None:
            return
        async with self._send_lock:
            from backend_A.ipc.frames import send_frame
            await send_frame(self._ipc_writer, msg)

    async def handle_incoming(self, msg: dict) -> None:
        """Handle an incoming message from B.

        Routes based on msg_type and tool:
        - pong: update heartbeat timestamp only
        - pose: update AppState + broadcast WS
        - telemetry: buffer for batch insert
        - status: update flight_status + broadcast WS
        - reject: notify alpha + broadcast WS
        - alert: trigger monitor handler
        """
        msg_type = msg.get("msg_type")
        tool = msg.get("tool")
        payload = msg.get("payload", {})

        if msg_type != MSG_EVENT:
            logger.debug(f"bridge: ignoring non-event from B: msg_type={msg_type}")
            return

        if tool == TOOL_PONG:
            self._handle_pong()
            return

        # All other events route through AppState and WS
        app = self._app_state
        if app is None:
            logger.warning("bridge: no AppState set, dropping message")
            return

        async with app.lock:
            if tool == "pose":
                app.update_pose(payload)
                await self._broadcast_ws({"type": "pose", "schema_version": 1, **payload})

            elif tool == "telemetry":
                app.telemetry_buffer.append(payload)

            elif tool == "status":
                app.flight_status = payload.get("flightStatus", app.flight_status)
                await self._broadcast_ws({"type": "status", "schema_version": 1, **payload})

            elif tool == "reject":
                app.add_alpha_input(f"[reject] {payload.get('reason', '')} — retry")
                await self._broadcast_ws({"type": "reject", "schema_version": 1, **payload})

            elif tool == TOOL_ALERT:
                if self._monitor_trigger:
                    await self._monitor_trigger.handle_alert(payload)
                await self._broadcast_ws({"type": "alert", "schema_version": 1, **payload})

            else:
                logger.debug(f"bridge: unhandled event tool='{tool}'")

    def _handle_pong(self) -> None:
        """Update pong timestamp. Called from IPC layer or bridge."""
        import time
        if self._app_state:
            self._app_state.last_pong_at = time.time()
            if not self._app_state.ipc_connected:
                self._app_state.ipc_connected = True

    async def _broadcast_ws(self, msg: dict) -> None:
        """Send a message to all connected WebSocket clients."""
        import json
        app = self._app_state
        if app is None:
            return
        dead = set()
        payload = json.dumps(msg, ensure_ascii=False)
        for ws in list(app.ws_connections):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)
        app.ws_connections -= dead
