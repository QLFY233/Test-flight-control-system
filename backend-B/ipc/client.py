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

# B-17: 重连指数退避上限 (固定 1s → 1/2/4/.../30s; 不写入 shared/protocol.py, 避免触碰跨侧协议常量)
_RECONNECT_BACKOFF_MAX = 30.0


class IpcClient:
    """B 侧 IPC client, 维护到 A 的持久连接。"""

    def __init__(self, state):
        self._state = state
        self._sock: socket.socket | None = None
        self._lock = threading.Lock()
        self._running = False
        self._on_frame = None  # 收到帧的回调 (由 dispatch 设置)
        self._on_disconnect = None  # 意外断连回调 (由 lifecycle/run_b 设置 → small_model 切 hover)
        self._connect_attempts = 0  # B-17: 连续连接失败计数 (日志)

    def set_frame_handler(self, handler):
        """设置 A→B 帧处理器 (dispatch.handle_incoming)。"""
        self._on_frame = handler

    def set_disconnect_handler(self, handler):
        """设置意外断连回调 (契约 §6: 断连 → small_model 切 hover)。"""
        self._on_disconnect = handler

    def connect(self) -> bool:
        """尝试连接 A。返回是否成功。"""
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(3.0)
            s.connect(IPC_SOCKET_PATH)
            # B-7: 5s 短超时替代阻塞模式 — 防止 sendall/recv 永久卡死持锁线程;
            # A 侧每 2s ping, 正常情况 5s 内必有数据, 超时即视为连接失效走重连。
            s.settimeout(5.0)
            with self._lock:
                if self._sock:
                    try:
                        self._sock.close()
                    except Exception:
                        pass
                self._sock = s
            self._state.ipc_connected = True
            self._connect_attempts = 0
            logger.info(f"[ipc-client] connected to A at {IPC_SOCKET_PATH}")
            return True
        except Exception as e:
            self._connect_attempts += 1
            logger.warning(f"[ipc-client] connect failed (attempt {self._connect_attempts}): {e}")
            return False

    def send(self, data: bytes):
        """发送原始字节 (4字节长度前缀 + msgpack 载荷)。

        B-7: 保持锁内 sendall 以保证多发送方帧不交错 (移出锁会坏帧);
        由 5s socket 超时兜底 — 若 A 停止读取导致 sendall 阻塞, 超时抛异常 →
        ipc_connected=False, 下轮 recv_loop 断连重连, 不会永久卡死持锁线程。
        """
        with self._lock:
            if self._sock is None:
                raise ConnectionError("Not connected")
            try:
                self._sock.sendall(data)
            except Exception:
                self._state.ipc_connected = False
                raise

    def _notify_disconnect(self):
        """触发断连回调 (small_model 切 hover)。"""
        if self._on_disconnect:
            try:
                self._on_disconnect()
            except Exception:
                logger.exception("[ipc-client] disconnect handler error")

    def recv_loop(self):
        """接收循环 — 阻塞读取帧, 调用 on_frame 回调。在独立线程运行。
        当连接断开或初始连接失败时自动重连 (指数退避 1s→30s)。"""
        self._running = True
        backoff = IPC_RECONNECT_INTERVAL
        while self._running:
            sock = None
            with self._lock:
                sock = self._sock

            if sock is None:
                # 未连接 — 尝试重连 (指数退避, B-17)
                if self.connect():
                    backoff = IPC_RECONNECT_INTERVAL
                else:
                    time.sleep(backoff)
                    backoff = min(backoff * 2.0, _RECONNECT_BACKOFF_MAX)
                continue

            try:
                from ipc.frames import recv_frame
                msg = recv_frame(sock)
                # B-4: 顶层必须为 dict, 否则按协议错误处理 (A 侧不可能发合法非 dict 帧)
                if not isinstance(msg, dict):
                    raise ValueError(f"received non-dict frame: {type(msg).__name__}")
                if self._on_frame:
                    try:
                        self._on_frame(msg)
                    except Exception:
                        # B-4: 回调异常不杀死 recv 线程 (daemon 线程静默死亡 = 永久断链)
                        logger.exception("[ipc-client] frame handler error")
            except (ConnectionError, OSError, ValueError) as e:
                logger.warning(f"[ipc-client] recv error: {e}")
                self._state.ipc_connected = False
                self._notify_disconnect()
                with self._lock:
                    try:
                        if self._sock:
                            self._sock.close()
                    except Exception:
                        pass
                    self._sock = None
                # 重连循环 (指数退避, B-17)
                while self._running and not self.connect():
                    time.sleep(backoff)
                    backoff = min(backoff * 2.0, _RECONNECT_BACKOFF_MAX)
                backoff = IPC_RECONNECT_INTERVAL

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
