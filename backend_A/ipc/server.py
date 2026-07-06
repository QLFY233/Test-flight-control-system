"""Unix socket IPC server — A is the server, B connects as client.

Listens on /tmp/flight_control_AB.sock, accepts B connections,
recv frames in loop, dispatches via bridge.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Optional

from backend_A.bus.protocol import (
    SCHEMA_VERSION,
    MSG_CALL,
    TOOL_PING,
    TOOL_PONG,
    COMP_HEARTBEAT,
)
from backend_A.ipc.frames import send_frame, recv_frame

logger = logging.getLogger(__name__)

SOCK_PATH = "/tmp/flight_control_AB.sock"
PING_INTERVAL = 2.0  # seconds
PONG_TIMEOUT = 5.0   # seconds → consider disconnected


class IPCServer:
    """Unix socket IPC server for A↔B communication."""

    def __init__(self, bridge: Any, app_state: Any) -> None:
        self._bridge = bridge
        self._app_state = app_state
        self._server: Optional[asyncio.AbstractServer] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        """Start the IPC server — remove stale socket, bind, listen."""
        # Remove stale socket if exists
        try:
            os.unlink(SOCK_PATH)
        except OSError:
            pass

        self._server = await asyncio.start_unix_server(
            self._handle_client, path=SOCK_PATH
        )
        self._running = True
        logger.info(f"ipc/server: listening on {SOCK_PATH}")

        # Start heartbeat task
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def stop(self) -> None:
        """Stop the IPC server."""
        self._running = False

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        try:
            os.unlink(SOCK_PATH)
        except OSError:
            pass

        logger.info("ipc/server: stopped")

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Handle a new B connection."""
        peer = writer.get_extra_info('peername')
        logger.info(f"ipc/server: B connected from {peer}")

        # Register writer with bridge
        self._bridge.set_writer(writer)
        self._app_state.ipc_connected = True
        self._app_state.last_pong_at = time.time()

        try:
            while self._running:
                try:
                    msg = await recv_frame(reader)
                    await self._bridge.handle_incoming(msg)
                except asyncio.IncompleteReadError:
                    logger.warning("ipc/server: B disconnected (EOF)")
                    break
                except Exception as exc:
                    logger.error(f"ipc/server: error reading frame: {exc}")
                    break
        finally:
            self._bridge.clear_writer()
            self._app_state.ipc_connected = False
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            logger.info("ipc/server: B connection closed")

    async def _heartbeat_loop(self) -> None:
        """Send ping every PING_INTERVAL, check pong timeout."""
        while self._running:
            await asyncio.sleep(PING_INTERVAL)

            if not self._bridge.is_connected:
                continue

            # Send ping
            try:
                ping_msg = {
                    "schema_version": SCHEMA_VERSION,
                    "from": "A",
                    "to": COMP_HEARTBEAT,
                    "msg_type": MSG_CALL,
                    "call_id": f"ping_{int(time.time())}",
                    "tool": TOOL_PING,
                    "args": {},
                    "payload": {},
                    "ts": time.time(),
                }
                await self._bridge.send_call(ping_msg)
            except Exception as exc:
                logger.warning(f"ipc/server: ping failed: {exc}")

            # Check pong timeout
            elapsed = time.time() - self._app_state.last_pong_at
            if self._app_state.ipc_connected and elapsed > PONG_TIMEOUT:
                logger.warning(f"ipc/server: pong timeout ({elapsed:.1f}s > {PONG_TIMEOUT}s)")
                self._app_state.ipc_connected = False
