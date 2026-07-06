"""
IPC client thread for Backend B.

Connects to Backend A's Unix domain socket as a CLIENT.
- Constant-time reconnect every 1 second when disconnected.
- Reads incoming frames and dispatches via the bus router.
- Sends outgoing messages (alerts, telemetry, events) to A.
- Maintains BState.ipc_connected flag.
"""

import socket
import time
import threading
import logging
from typing import Optional

from backend_B.bus.protocol import (
    MSG_CALL, MSG_RESULT, MSG_EVENT, MSG_ERROR,
    TOOL_PING, TOOL_PONG,
)
from backend_B.ipc.frames import send_frame_sync, recv_frame_sync
from backend_B.bus.router import route

logger = logging.getLogger("backend_b.ipc_client")

# Reconnect interval in seconds
RECONNECT_INTERVAL = 1.0

# Default socket path
DEFAULT_SOCKET_PATH = "/tmp/flight_control_AB.sock"


class IpcClient:
    """
    IPC client that maintains a connection to Backend A.

    Runs in a dedicated thread. Handles reconnection, receiving,
    and dispatching of messages.
    """

    def __init__(
        self,
        socket_path: str = DEFAULT_SOCKET_PATH,
        bstate=None,
    ):
        self._socket_path = socket_path
        self._bstate = bstate
        self._sock: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Lock for thread-safe send operations
        self._send_lock = threading.Lock()

    # ---- lifecycle ----

    def start(self) -> None:
        """Start the IPC client thread."""
        if self._running:
            logger.warning("IPC client already running")
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, name="ipc-client", daemon=True)
        self._thread.start()
        logger.info("IPC client thread started")

    def stop(self) -> None:
        """Stop the IPC client thread."""
        self._running = False
        # Close socket to unblock recv
        self._close_socket()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("IPC client thread stopped")

    def is_running(self) -> bool:
        return self._running

    # ---- send ----

    def send(self, msg: dict) -> bool:
        """
        Send a message to Backend A (thread-safe).

        Returns True on success, False on failure.
        """
        with self._send_lock:
            sock = self._sock
            if sock is None:
                logger.warning("Cannot send: not connected")
                return False
            try:
                send_frame_sync(sock, msg)
                return True
            except Exception as exc:
                logger.error("Send failed: %s", exc)
                self._bstate.ipc_connected = False
                self._close_socket()
                return False

    def send_event(self, event_name: str, data: dict) -> bool:
        """Convenience: send an 'event' message."""
        return self.send({
            "type": MSG_EVENT,
            "event": event_name,
            "data": data,
        })

    def send_result(self, call_id: int, tool: str, result: dict) -> bool:
        """Convenience: send a 'result' message."""
        return self.send({
            "type": MSG_RESULT,
            "id": call_id,
            "tool": tool,
            "result": result,
        })

    def send_error(self, call_id: int, tool: str, error: str) -> bool:
        """Convenience: send an 'error' message."""
        return self.send({
            "type": MSG_ERROR,
            "id": call_id,
            "tool": tool,
            "error": error,
        })

    # ---- internal ----

    def _run(self) -> None:
        """Main loop: connect, read frames, reconnect on failure."""
        while self._running:
            if not self._ensure_connected():
                time.sleep(RECONNECT_INTERVAL)
                continue

            try:
                msg = recv_frame_sync(self._sock)
                if msg:
                    self._handle_message(msg)
            except (ConnectionError, OSError) as exc:
                logger.warning("Connection lost: %s", exc)
                self._bstate.ipc_connected = False
                self._close_socket()
            except ValueError as exc:
                logger.error("Frame decode error: %s", exc)
                self._bstate.ipc_connected = False
                self._close_socket()
            except Exception as exc:
                logger.exception("Unexpected error in IPC loop: %s", exc)
                self._bstate.ipc_connected = False
                self._close_socket()

    def _ensure_connected(self) -> bool:
        """Try to connect. Return True if connected."""
        if self._sock is not None:
            return True

        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(1.0)
            sock.connect(self._socket_path)
            sock.settimeout(None)  # Blocking after connect
            self._sock = sock
            self._bstate.ipc_connected = True
            logger.info("Connected to %s", self._socket_path)
            return True
        except (FileNotFoundError, ConnectionRefusedError):
            logger.debug("Socket not available at %s (retry in %ss)",
                         self._socket_path, RECONNECT_INTERVAL)
            return False
        except Exception as exc:
            logger.debug("Connection attempt failed: %s", exc)
            return False

    def _close_socket(self) -> None:
        """Close the socket if open."""
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        self._bstate.ipc_connected = False

    def _handle_message(self, msg: dict) -> None:
        """
        Handle an incoming message from A.

        Dispatches via router and sends response back if needed.
        """
        msg_type = msg.get("type", "")

        if msg_type == MSG_CALL:
            tool = msg.get("tool", "")
            call_id = msg.get("id", 0)

            # Handle ping specially for fast pong
            if tool == TOOL_PING:
                self.send_result(call_id, TOOL_PONG, {"pong": True})
                return

            # Route to bus components
            if self._bstate is not None:
                response = route(msg, self._bstate)
                if response is not None:
                    # If router returns a dict, send it back
                    if response.get("type") == MSG_RESULT:
                        self.send(response)
                    elif response.get("type") == MSG_ERROR:
                        self.send(response)
                    else:
                        self.send(response)
            else:
                self.send_error(call_id, tool, "BState not initialized")

        elif msg_type == MSG_RESULT:
            # A-side response to a B-originated call (e.g., telemetry acknowledgment)
            logger.debug("Received result from A: id=%s", msg.get("id"))

        elif msg_type == MSG_EVENT:
            # Incoming event from A
            if self._bstate is not None:
                route(msg, self._bstate)
            else:
                logger.debug("Dropping event (no bstate): %s", msg)

        elif msg_type == MSG_ERROR:
            logger.warning("Received error from A: %s", msg)

        else:
            logger.warning("Unknown incoming message type: %s", msg_type)
