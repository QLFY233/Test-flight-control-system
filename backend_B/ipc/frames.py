"""
Synchronous frame codec for Backend B IPC (Unix domain socket).

B side uses threading (not asyncio), so all I/O is synchronous.
Frames are: 4-byte big-endian length prefix + msgpack payload.

Mirrors backend-A/ipc/frames.py exactly.
"""

import struct
import socket
import msgpack
import logging

from backend_B.bus.protocol import MSGPACK_USE_BIN_TYPE

logger = logging.getLogger("backend_b.ipc")

MAX_FRAME_SIZE = 16 * 1024 * 1024  # 16 MiB


def send_frame_sync(sock: socket.socket, msg: dict) -> None:
    """
    Pack and send a single message frame over the socket.

    Format: [4-byte BE length][msgpack payload]

    Args:
        sock: Connected socket (must be blocking).
        msg: Message dict to encode and send.

    Raises:
        BrokenPipeError: If the connection is broken.
        OSError: On socket errors.
    """
    payload = msgpack.packb(msg, use_bin_type=MSGPACK_USE_BIN_TYPE)
    length = len(payload)

    if length > MAX_FRAME_SIZE:
        raise ValueError(
            f"Frame too large: {length} bytes (max {MAX_FRAME_SIZE})"
        )

    # Send 4-byte big-endian length prefix
    length_prefix = struct.pack(">I", length)
    sock.sendall(length_prefix)

    # Send payload
    sock.sendall(payload)

    logger.debug("Sent frame: %d bytes, type=%s", length, msg.get("type", "?"))


def recv_frame_sync(sock: socket.socket) -> dict:
    """
    Receive and unpack a single message frame from the socket.

    Blocks until a complete frame is available.

    Returns:
        Decoded message dict.

    Raises:
        ConnectionError: If the connection is closed cleanly.
        OSError: On socket errors.
        ValueError: If the frame exceeds MAX_FRAME_SIZE or is malformed.
    """
    # Read 4-byte length prefix
    length_bytes = _recv_exact(sock, 4)
    length = struct.unpack(">I", length_bytes)[0]

    if length > MAX_FRAME_SIZE:
        raise ValueError(
            f"Frame too large: {length} bytes (max {MAX_FRAME_SIZE})"
        )

    # Read payload
    payload = _recv_exact(sock, length)

    # Unpack
    msg = msgpack.unpackb(payload, use_bin_type=MSGPACK_USE_BIN_TYPE, raw=False)
    logger.debug("Received frame: %d bytes, type=%s", length, msg.get("type", "?"))
    return msg


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    """
    Read exactly n bytes from the socket, blocking as needed.

    Args:
        sock: Connected socket.
        n: Number of bytes to read.

    Returns:
        Exactly n bytes.

    Raises:
        ConnectionError: If the peer closes the connection before n bytes are read.
        OSError: On socket errors.
    """
    buf = bytearray()
    remaining = n

    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ConnectionError(
                f"Connection closed after reading {len(buf)} of {n} bytes"
            )
        buf.extend(chunk)
        remaining -= len(chunk)

    return bytes(buf)
