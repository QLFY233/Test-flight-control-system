"""Async frame codec for A↔B IPC.

Uses length-prefixed msgpack frames over a stream.
"""

from __future__ import annotations

import asyncio
import struct
import msgpack
import logging

logger = logging.getLogger(__name__)

MAX_FRAME_SIZE = 16 * 1024 * 1024  # 16 MiB


async def send_frame(writer: asyncio.StreamWriter, msg: dict) -> None:
    """Pack a message dict into a length-prefixed frame and send."""
    payload = msgpack.packb(msg, use_bin_type=True)
    if len(payload) > MAX_FRAME_SIZE:
        raise ValueError(f"Frame exceeds MAX_FRAME_SIZE: {len(payload)} > {MAX_FRAME_SIZE}")

    header = struct.pack(">I", len(payload))
    writer.write(header + payload)
    await writer.drain()


async def recv_frame(reader: asyncio.StreamReader) -> dict:
    """Read a length-prefixed frame and unpack to a message dict."""
    # Read 4-byte length prefix
    header_bytes = await reader.readexactly(4)
    (length,) = struct.unpack(">I", header_bytes)

    if length > MAX_FRAME_SIZE:
        raise ValueError(f"Frame too large: {length} > {MAX_FRAME_SIZE}")

    payload = await reader.readexactly(length)
    return msgpack.unpackb(payload, raw=False, use_bin_type=True)
