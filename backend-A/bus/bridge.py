"""
A↔B IPC 桥接 — A 内总线消息经 IPC 转发给 B。
B→A inbound event 经此注入 A 总线分发。
"""
import time
import logging

from bus.protocol import (
    SCHEMA_VERSION, MSG_TYPE_CALL, MSG_TYPE_RESULT,
    TO_ALPHA, TO_BETA,
    EVENT_TOOL_POSE, EVENT_TOOL_TELEMETRY, EVENT_TOOL_STATUS,
    EVENT_TOOL_REJECT, EVENT_TOOL_ALERT,
)

logger = logging.getLogger(__name__)

# 🟡-4: 各 B→A event.tool 应携带的 to 组件 (冻结文档 §3: 未知/错配 to 视为协议错误丢弃)
_EVENT_EXPECTED_TO = {
    EVENT_TOOL_POSE: TO_ALPHA,
    EVENT_TOOL_TELEMETRY: TO_ALPHA,
    EVENT_TOOL_STATUS: TO_ALPHA,
    EVENT_TOOL_REJECT: TO_ALPHA,
    EVENT_TOOL_ALERT: TO_BETA,
}

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

    # 🟡-4: 校验 to — 不匹配即记日志丢弃 (契约防御)
    expected_to = _EVENT_EXPECTED_TO.get(tool)
    if expected_to is not None and msg.get("to") != expected_to:
        logger.warning(
            f"[bridge] event tool={tool} to={msg.get('to')!r} != expected "
            f"{expected_to!r}, dropping"
        )
        return

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
#
# payload 字段映射 (接口冻结 §3 §5):
#   B→A event 使用 camelCase 键名 (angularVel, flightStatus, actionIndex, etc.)
#   此处转换为内部 snake_case 后调用 state / bus 接口
#   pose payload 字段顺序必须为 [pos, quat(w,x,y,z), vel, accel, angularVel, ts]

_state_ref = None  # 由 lifecycle 设置
_tel_buffer_ref = None  # 由 lifecycle 设置，用于 pose 注入遥测缓冲
_alpha_loop_ref = None  # 由 lifecycle 设置，用于 reject 注入 α 上下文

# WS broadcast 回调 (由 lifecycle 注入)
_ws_pose = None
_ws_alert = None
_ws_status = None
_ws_reject = None
_ws_link = None


def set_state(state):
    global _state_ref
    _state_ref = state


def set_telemetry_buffer(buf):
    """设置 TelemetryBuffer 引用 (由 lifecycle 调用)。"""
    global _tel_buffer_ref
    _tel_buffer_ref = buf


def set_alpha_loop(loop):
    """设置 α loop 引用 (由 lifecycle 调用，用于 reject 注入)。"""
    global _alpha_loop_ref
    _alpha_loop_ref = loop


def set_ws_broadcast(pose_fn, alert_fn, status_fn, reject_fn=None, link_fn=None):
    """注入 WebSocket broadcast 函数 (由 lifecycle 调用)。"""
    global _ws_pose, _ws_alert, _ws_status, _ws_reject, _ws_link
    _ws_pose = pose_fn
    _ws_alert = alert_fn
    _ws_status = status_fn
    _ws_reject = reject_fn
    _ws_link = link_fn


async def _handle_pose(payload: dict):
    """B→A pose event (10Hz)。
    更新 AppState.current_pose, 注入 TelemetryBuffer, 广播 WS。
    """
    pos = payload.get("pos", [0, 0, 0])
    quat = payload.get("quat", [1, 0, 0, 0])
    vel = payload.get("vel", [0, 0, 0])
    accel = payload.get("accel", [0, 0, 0])
    angular_vel = payload.get("angularVel", [0, 0, 0])
    ts = payload.get("ts", time.time())

    if _state_ref:
        await _state_ref.update_pose(pos, quat, vel, accel, angular_vel, ts)

    # WS broadcast — B2 修复后 broadcast 为非阻塞入队, 不再拖慢 IPC 收帧循环;
    # N1: 位姿更新/缓冲为内存操作, 队列化 WS 后此处已无阻塞点
    if _ws_pose:
        try:
            await _ws_pose(pos, quat, vel, accel, angular_vel, ts)
        except Exception:
            pass

    # 遥测缓冲
    if _tel_buffer_ref and _state_ref and _state_ref.session_id:
        await _tel_buffer_ref.append({
            "session_id": _state_ref.session_id,
            "t": ts,
            "pos": pos, "quat": quat, "vel": vel,
            "accel": accel, "angular_vel": angular_vel,
        })


async def _handle_telemetry(payload: dict):
    # 先导: 仅日志, 阶段C 实现遥测缓冲
    logger.debug(f"[bridge] telemetry received, ts={payload.get('ts')}")


async def _handle_status(payload: dict):
    flight_status = payload.get("flightStatus", "idle")
    if _state_ref:
        _state_ref.flight_status = flight_status
    # 🔴-4: 转发 WS status (冻结文档 §5) — 此前 broadcast_status 全仓无调用点,
    # 前端永远收不到任务进度
    if _ws_status:
        try:
            await _ws_status(
                flight_status,
                payload.get("mode", "manual"),
                payload.get("currentAction", 0),
                payload.get("totalActions", 0),
                payload.get("progress", 0),
            )
        except Exception:
            pass
    logger.info(f"[bridge] status: {payload}")


async def _handle_reject(payload: dict):
    reason = payload.get("reason", "unknown")
    action_index = payload.get("actionIndex", 0)
    logger.warning(f"[bridge] REJECT: reason={reason} actionIndex={action_index}")
    # 🟡-6: reject 注入 α — 清空 A 侧计划 + 兜底 hover。
    # 原注释"α 下轮 tick 会发送 hover"不成立: _tick 在计划非空时 pass, 永不回退。
    if _state_ref:
        _state_ref.current_action_plan = None
    if _alpha_loop_ref:
        try:
            await _alpha_loop_ref.emergency_hover()
        except Exception:
            pass
    # WS broadcast reject
    if _ws_reject:
        try:
            await _ws_reject(reason, action_index, payload.get("suggestedAction"))
        except Exception:
            pass


async def _handle_alert(payload: dict):
    logger.warning(f"[bridge] ALERT: level={payload.get('level')} code={payload.get('code')} detail={payload.get('detail')}")
    # WS broadcast
    if _ws_alert:
        try:
            await _ws_alert(
                payload.get("level", "warning"),
                payload.get("code", "unknown"),
                payload.get("detail", ""),
                payload.get("suggestion"),
            )
        except Exception:
            pass
