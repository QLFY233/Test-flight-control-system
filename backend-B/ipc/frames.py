"""
长度前缀 msgpack 帧编解码 — A↔B IPC 传输层。
与 docs/specs/总体/2026-07-05-A-B-接口冻结.md §1 绑定。
"""

import struct
import msgpack

from bus.protocol import MSGPACK_USE_BIN_TYPE, IPC_FRAME_MAX_BYTES


def encode_frame(payload: dict) -> bytes:
    """
    将 dict 编码为长度前缀帧字节串 (4 字节大端长度 + msgpack 载荷)。
    供 send_frame 和 IPC dispatch 共用。
    """
    data = msgpack.packb(payload, use_bin_type=MSGPACK_USE_BIN_TYPE)
    if len(data) > IPC_FRAME_MAX_BYTES:
        raise ValueError(f"Frame too large: {len(data)} bytes (max {IPC_FRAME_MAX_BYTES})")
    header = struct.pack(">I", len(data))
    return header + data


def send_frame(sock, payload: dict) -> None:
    """
    发送一帧：4 字节大端 unsigned int 长度前缀 + msgpack 载荷。
    payload 必须为 dict，内含 schema_version 等总线字段。
    """
    data = encode_frame(payload)
    sock.sendall(data)


def recv_frame(sock) -> dict:
    """
    接收一帧：读 4 字节长度前缀 → 读载荷 → msgpack 解包。
    返回 dict；连接关闭或帧超限抛异常。
    """
    header = _recv_exact(sock, 4)
    if not header:
        raise ConnectionError("Socket closed")
    length = struct.unpack(">I", header)[0]
    if length > IPC_FRAME_MAX_BYTES:
        raise ValueError(f"Frame too large: {length} bytes (max {IPC_FRAME_MAX_BYTES})")
    data = _recv_exact(sock, length)
    if len(data) < length:
        raise ConnectionError("Socket closed mid-frame")
    return msgpack.unpackb(data, raw=False)


def _recv_exact(sock, n: int) -> bytes:
    """读取恰好 n 字节的分段接收。"""
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            break
        buf.extend(chunk)
    return bytes(buf)
