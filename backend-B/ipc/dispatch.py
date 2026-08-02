"""
IPC 分发层 — A→B call 解帧进 B 总线; B→A event 封帧上行; ping→pong。
"""
import time
import logging

from bus.protocol import (
    SCHEMA_VERSION,
    MSG_TYPE_CALL, MSG_TYPE_EVENT, MSG_TYPE_ERROR,
    CALL_TOOL_ACTION, CALL_TOOL_ABORT, CALL_TOOL_HOVER, CALL_TOOL_PING,
    EVENT_TOOL_PONG,
    TO_SMALL_MODEL, TO_HEARTBEAT,
)
from bus import router as bus_router
from ipc.frames import send_frame

logger = logging.getLogger(__name__)


class Dispatch:
    """IPC 消息分发器。"""

    def __init__(self, state, ipc_client):
        self._state = state
        self._ipc = ipc_client

    def handle_incoming(self, msg: dict):
        """
        处理 A→B 的总线消息 (msgpack 已解包为 dict)。
        msg 含: schema_version, from, to, msg_type, call_id, tool, args, payload, ts
        """
        msg_type = msg.get("msg_type")
        tool = msg.get("tool", "")

        if msg_type == MSG_TYPE_CALL:
            self._handle_call(msg)
        elif msg_type == MSG_TYPE_EVENT and tool == CALL_TOOL_PING:
            self._handle_ping()
        else:
            logger.warning(f"[dispatch] unexpected msg_type={msg_type} tool={tool}")

    def _handle_call(self, msg: dict):
        """A→B call: 路由到 B 侧组件。"""
        tool = msg.get("tool")
        args = msg.get("args", {})
        call_id = msg.get("call_id", "")  # 保留以便后续启用 result 配对

        if tool == CALL_TOOL_PING:
            self._handle_ping()
            return

        # A→B call.tool 映射到 B 侧 small_model
        if tool in (CALL_TOOL_ACTION, CALL_TOOL_ABORT, CALL_TOOL_HOVER):
            sm_tool = {
                CALL_TOOL_ACTION: "generate_goal",
                CALL_TOOL_ABORT: "abort",
                CALL_TOOL_HOVER: "hover",
            }[tool]
            result = bus_router.call(to=TO_SMALL_MODEL, tool=sm_tool, args=args, _from="A")
            # 暂不回 result 给 A (fire-and-forget 先导)
            if result.get("msg_type") == MSG_TYPE_ERROR:
                logger.error(f"[dispatch] small_model error: {result}")
        else:
            logger.warning(f"[dispatch] unknown call tool: {tool}")

    def _handle_ping(self):
        """响应心跳 ping → pong。"""
        pong_msg = {
            "schema_version": SCHEMA_VERSION,
            "from": "B",
            "to": TO_HEARTBEAT,
            "msg_type": MSG_TYPE_EVENT,
            "call_id": "",
            "tool": EVENT_TOOL_PONG,
            "args": {},
            "payload": {},
            "ts": time.time(),
        }
        self.send_event(pong_msg)

    def send_event(self, msg: dict):
        """封帧发送 B→A event (复用 frames.encode_frame)。"""
        try:
            from ipc.frames import encode_frame
            data = encode_frame(msg)
            self._ipc.send(data)
        except Exception as e:
            logger.warning(f"[dispatch] send_event failed: {e}")
