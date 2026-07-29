"""
A↔B IPC client — B 侧主动连 A 的 Unix socket server。
恒定时间重连 (1s), socket 断 → ipc_connected=False。
"""
from __future__ import annotations
import socket
import time
import logging
import threading

from bus.protocol import IPC_SOCKET_PATH, IPC_RECONNECT_INTERVAL

logger = logging.getLogger(__name__)


class IpcClient:
    """B 侧 IPC client, 维护到 A 的持久连接。"""

    def __init__(self, state):
        self._state = state
        self._sock: socket.socket | None = None
        self._lock = threading.Lock()
        self._running = False
        self._on_frame = None  # 收到帧的回调 (由 dispatch 设置)

    def set_frame_handler(self, handler):
        """设置 A→B 帧处理器 (dispatch.handle_incoming)。"""
        self._on_frame = handler

    def connect(self) -> bool:
        """尝试连接 A。返回是否成功。"""
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(3.0)
            s.connect(IPC_SOCKET_PATH)
            s.settimeout(None)  # 阻塞模式
            with self._lock:
                if self._sock:
                    try:
                        self._sock.close()
                    except Exception:
                        pass
                self._sock = s
            self._state.ipc_connected = True
            logger.info(f"[ipc-client] connected to A at {IPC_SOCKET_PATH}")
            return True
        except Exception as e:
            logger.warning(f"[ipc-client] connect failed: {e}")
            return False

    def send(self, data: bytes):
        """发送原始字节 (4字节长度前缀 + msgpack 载荷)。"""
        with self._lock:
            if self._sock is None:
                raise ConnectionError("Not connected")
            try:
                self._sock.sendall(data)
            except Exception:
                self._state.ipc_connected = False
                raise

    def recv_loop(self):
        """接收循环 — 阻塞读取帧, 调用 on_frame 回调。在独立线程运行。
        当连接断开或初始连接失败时自动重连 (每 1s)。"""
        self._running = True
        while self._running:
            sock = None
            with self._lock:
                sock = self._sock

            if sock is None:
                # 未连接 — 尝试重连
                if not self.connect():
                    time.sleep(IPC_RECONNECT_INTERVAL)
                continue

            try:
                from ipc.frames import recv_frame
                msg = recv_frame(sock)
                if self._on_frame:
                    self._on_frame(msg)
            except (ConnectionError, OSError, ValueError) as e:
                logger.warning(f"[ipc-client] recv error: {e}")
                self._state.ipc_connected = False
                with self._lock:
                    try:
                        if self._sock:
                            self._sock.close()
                    except Exception:
                        pass
                    self._sock = None
                # 重连循环
                while self._running and not self.connect():
                    time.sleep(IPC_RECONNECT_INTERVAL)

    def close(self):
        """关闭连接。"""
        self._running = False
        with self._lock:
            if self._sock:
                try:
                    self._sock.close()
                except Exception:
                    pass
                self._sock = None
        self._state.ipc_connected = False
