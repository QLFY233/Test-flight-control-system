"""
A↔B IPC server — A 作 server, B 作 client。
Unix socket: bind + listen + accept, 长度前缀 msgpack 帧。
心跳: 2s ping, 5s 无 pong 断连。
"""
import os
import struct
import time
import asyncio
import logging

import msgpack

from bus.protocol import (
    SCHEMA_VERSION, IPC_SOCKET_PATH,
    IPC_PING_INTERVAL, IPC_PONG_TIMEOUT,
    MSGPACK_USE_BIN_TYPE, IPC_FRAME_MAX_BYTES,
    MSG_TYPE_EVENT, CALL_TOOL_PING, EVENT_TOOL_PONG,
    TO_HEARTBEAT,
)
from bus.bridge import dispatch_b_event, set_ipc_sender

logger = logging.getLogger(__name__)


class IpcServer:
    """A 侧 IPC server — 接受 B 连接, 收发帧。"""

    def __init__(self, state):
        self._state = state
        self._server: asyncio.AbstractServer | None = None
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._last_pong: float = 0.0
        self._running = False
        self._tasks: list[asyncio.Task] = []  # 后台 task 引用，用于 stop 时取消

    async def start(self):
        """启动 server, 监听 Unix socket。"""
        # 清理残留
        try:
            os.unlink(IPC_SOCKET_PATH)
        except FileNotFoundError:
            pass

        self._server = await asyncio.start_unix_server(
            self._handle_client, path=IPC_SOCKET_PATH
        )
        self._running = True
        logger.info(f"[ipc-server] listening on {IPC_SOCKET_PATH}")

        # 设置 bridge 的 IPC sender
        set_ipc_sender(self._send_and_wait)

        # 启动心跳 (保存 task 引用以便 stop 时取消)
        self._tasks.append(asyncio.create_task(self._ping_loop()))
        self._tasks.append(asyncio.create_task(self._pong_watchdog()))

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """新 B 连接建立。ipc_connected 延迟到首次 pong 才设为 True。"""
        addr = writer.get_extra_info('peername', 'unknown')
        logger.info(f"[ipc-server] B TCP connected from {addr}, awaiting first pong...")
        self._reader = reader
        self._writer = writer
        # 不在 TCP 握手阶段标记 connected — 等首次 pong 验证后由 _recv_loop 设置
        self._last_pong = time.time()  # 给首次 pong 留 5s 窗口

        try:
            await self._recv_loop(reader)
        except Exception as e:
            logger.warning(f"[ipc-server] recv error: {e}")
        finally:
            self._state.ipc_connected = False
            self._reader = None
            self._writer = None
            logger.info("[ipc-server] B disconnected")

    async def _recv_loop(self, reader: asyncio.StreamReader):
        """接收循环 — 读帧 → 分发。帧过大时断开连接。"""
        while self._running:
            # 读 4 字节长度
            header = await reader.readexactly(4)
            length = struct.unpack(">I", header)[0]
            if length > IPC_FRAME_MAX_BYTES:
                logger.error(f"[ipc-server] frame too large: {length} > {IPC_FRAME_MAX_BYTES}, disconnecting")
                return  # 断开连接，继续读取会导致帧边界错乱
            # 读载荷
            data = await reader.readexactly(length)
            msg = msgpack.unpackb(data, raw=False)

            msg_type = msg.get("msg_type")
            tool = msg.get("tool", "")

            if msg_type == MSG_TYPE_EVENT and tool == EVENT_TOOL_PONG:
                # 版本协商: 验证 B 侧 schema_version 与 A 侧一致
                b_version = msg.get("schema_version")
                if b_version != SCHEMA_VERSION:
                    logger.error(
                        f"[ipc-server] schema version mismatch! A={SCHEMA_VERSION} B={b_version}. "
                        "Disconnecting — 两侧必须升级到相同版本。"
                    )
                    self._state.ipc_connected = False
                    if self._writer and not self._writer.is_closing():
                        self._writer.close()
                    return
                self._last_pong = time.time()
                self._state.last_pong_at = self._last_pong
                if not self._state.ipc_connected:
                    self._state.ipc_connected = True
                    logger.info("[ipc-server] B verified (first pong received)")
            elif msg_type == MSG_TYPE_EVENT:
                # B→A event → 注入 A 总线
                await dispatch_b_event(msg)
            else:
                logger.warning(f"[ipc-server] unexpected msg_type={msg_type} tool={tool}")

    async def _send_and_wait(self, msg: dict) -> dict:
        """发送帧给 B (bridge 用)。先导 fire-and-forget, 返回 ack。"""
        if self._writer is None:
            raise ConnectionError("B not connected")
        data = msgpack.packb(msg, use_bin_type=MSGPACK_USE_BIN_TYPE)
        header = struct.pack(">I", len(data))
        self._writer.write(header + data)
        await self._writer.drain()
        return {"status": "sent"}  # 先导不等待 result

    async def _ping_loop(self):
        """心跳 ping — 每 2s 发一次。"""
        while self._running:
            await asyncio.sleep(IPC_PING_INTERVAL)
            if self._writer and not self._writer.is_closing():
                try:
                    ping = {
                        "schema_version": SCHEMA_VERSION,
                        "from": "A",
                        "to": TO_HEARTBEAT,
                        "msg_type": MSG_TYPE_EVENT,
                        "call_id": "",
                        "tool": CALL_TOOL_PING,
                        "args": {},
                        "payload": {},
                        "ts": time.time(),
                    }
                    data = msgpack.packb(ping, use_bin_type=MSGPACK_USE_BIN_TYPE)
                    self._writer.write(struct.pack(">I", len(data)) + data)
                    await self._writer.drain()
                except Exception as e:
                    logger.warning(f"[ipc-server] ping failed: {e}")

    async def _pong_watchdog(self):
        """pong 超时检测 — 5s 无 pong 视断连。"""
        while self._running:
            await asyncio.sleep(1.0)
            if self._state.ipc_connected:
                elapsed = time.time() - self._last_pong
                if elapsed > IPC_PONG_TIMEOUT:
                    logger.warning(f"[ipc-server] pong timeout ({elapsed:.1f}s), marking B disconnected")
                    self._state.ipc_connected = False
                    if self._writer and not self._writer.is_closing():
                        self._writer.close()
                    self._reader = None
                    self._writer = None

    async def stop(self):
        """关停 server。"""
        self._running = False
        # 取消后台 task (ping_loop / pong_watchdog)
        for t in self._tasks:
            if not t.done():
                t.cancel()
        # 等待 task 退出 (忽略 CancelledError)
        for t in self._tasks:
            try:
                await t
            except asyncio.CancelledError:
                pass
        self._tasks.clear()
        if self._writer and not self._writer.is_closing():
            self._writer.close()
        if self._server:
            self._server.close()
        try:
            os.unlink(IPC_SOCKET_PATH)
        except FileNotFoundError:
            pass
        logger.info("[ipc-server] stopped")
