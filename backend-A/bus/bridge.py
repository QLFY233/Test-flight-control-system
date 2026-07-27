"""
A↔B IPC 桥接 — A 内总线消息经 IPC 转发给 B。
B→A inbound event 经此注入 A 总线分发。
"""
import time
import logging

from bus.protocol import SCHEMA_VERSION, MSG_TYPE_CALL, MSG_TYPE_RESULT

logger = logging.getLogger(__name__)

# 由 ipc/server.py 在启动时设置
_ipc_sender = None  # async callable: send_and_wait(msg) -> dict


def set_ipc_sender(sender):
    """设置 IPC 发送器 (由 ipc/server 调用)。"""
    global _ipc_sender
    _ipc_sender = sender


async def forward_to_b(to: str, tool: str, args: dict, _from: str, call_id: str) -> dict:
    """A→B 转发: 封帧发 B, (先导 fire-and-forget, 返回 ack)。"""
    if _ipc_sender is None:
        raise RuntimeError("IPC sender not initialized")

    msg = {
        "schema_version": SCHEMA_VERSION,
        "from": _from,
        "to": to,
        "msg_type": MSG_TYPE_CALL,
        "call_id": call_id,
        "tool": tool,
        "args": args,
        "payload": {},
        "ts": time.time(),
    }

    try:
        result = await _ipc_sender(msg)
        return result
    except Exception as exc:
        logger.error(f"[bridge] forward to B failed: {exc}")
        raise


async def dispatch_b_event(msg: dict):
    """
    B→A inbound event 注入 A 总线分发。
    由 ipc/server 在收到 B 帧时调用。
    """
    tool = msg.get("tool", "")
    payload = msg.get("payload", {})

    if tool == "pose":
        await _handle_pose(payload)
    elif tool == "telemetry":
        await _handle_telemetry(payload)
    elif tool == "status":
        await _handle_status(payload)
    elif tool == "reject":
        await _handle_reject(payload)
    elif tool == "alert":
        await _handle_alert(payload)
    else:
        logger.warning(f"[bridge] unhandled B→A event tool={tool}")


# ── B→A event handlers (stub in stage C, full in stage G/H) ──

_state_ref = None  # 由 lifecycle 设置


def set_state(state):
    global _state_ref
    _state_ref = state


async def _handle_pose(payload: dict):
    if _state_ref:
        await _state_ref.update_pose(
            payload.get("pos", [0, 0, 0]),
            payload.get("quat", [1, 0, 0, 0]),
            payload.get("vel", [0, 0, 0]),
            payload.get("accel", [0, 0, 0]),
            payload.get("angularVel", [0, 0, 0]),
            payload.get("ts", time.time()),
        )


async def _handle_telemetry(payload: dict):
    # 先导: 仅日志, 阶段C 实现遥测缓冲
    logger.debug(f"[bridge] telemetry received, ts={payload.get('ts')}")


async def _handle_status(payload: dict):
    if _state_ref:
        _state_ref.flight_status = payload.get("flightStatus", "idle")
    logger.info(f"[bridge] status: {payload}")


async def _handle_reject(payload: dict):
    logger.warning(f"[bridge] REJECT: reason={payload.get('reason')} actionIndex={payload.get('actionIndex')}")


async def _handle_alert(payload: dict):
    logger.warning(f"[bridge] ALERT: level={payload.get('level')} code={payload.get('code')} detail={payload.get('detail')}")
