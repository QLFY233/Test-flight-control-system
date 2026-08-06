"""
WebSocket 处理 — 实时数据下行 (pose/status/reject/alert/alpha_output/...)。
接收前端 sync/voice_frame/tts_request, 推送飞行状态。
"""
import json
import time
import asyncio
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from bus.protocol import SCHEMA_VERSION

logger = logging.getLogger(__name__)

router = APIRouter()

# B2: 每个前端客户端一个独立 sender task + 有界发送队列。
# broadcast 只 put_nowait 入队 (非阻塞) — 慢客户端不再持锁阻塞全部广播,
# 也不再拖慢 IPC 收帧路径 (pose 10Hz 广播原与收帧循环串行 await)。
_clients: dict[WebSocket, asyncio.Queue] = {}
_clients_lock = asyncio.Lock()
_QUEUE_MAX = 256          # 10Hz pose → ~25s 缓冲
_WS_MSG_MAX = 64 * 1024   # S2: 单条上行消息上限

# 全局引用
_state_ref = None


def set_ws_context(state):
    global _state_ref
    _state_ref = state


async def _client_sender(ws: WebSocket, queue: asyncio.Queue):
    """单客户端发送 task — 串行消费队列; 出错或收到关闭哨兵即退出。"""
    try:
        while True:
            payload = await queue.get()
            if payload is None:  # 关闭哨兵
                break
            try:
                await ws.send_text(payload)
            except Exception:
                break
    finally:
        await _remove_client(ws)


async def _add_client(ws: WebSocket):
    queue = asyncio.Queue(maxsize=_QUEUE_MAX)
    async with _clients_lock:
        _clients[ws] = queue
    asyncio.create_task(_client_sender(ws, queue))


async def _remove_client(ws: WebSocket):
    async with _clients_lock:
        queue = _clients.pop(ws, None)
    if queue is not None:
        try:
            queue.put_nowait(None)
        except asyncio.QueueFull:
            pass


async def broadcast(msg: dict):
    """向所有已连接前端推送消息 (非阻塞入队, 队列满即断开慢客户端)。"""
    payload = json.dumps(msg, ensure_ascii=False)
    async with _clients_lock:
        targets = list(_clients.items())
    for ws, queue in targets:
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            # 客户端消费太慢 → 主动断开, 避免无界积压
            logger.warning("[ws] client too slow, dropping connection")
            try:
                await ws.close()
            except Exception:
                pass
            await _remove_client(ws)


async def broadcast_pose(pos, quat, vel, accel, angular_vel, ts):
    """推送位姿 (10Hz, 由 bridge._handle_pose 调用)。"""
    await broadcast({
        "type": "pose",
        "schema_version": SCHEMA_VERSION,
        "pos": pos,
        "quat": quat,
        "vel": vel,
        "accel": accel,
        "angularVel": angular_vel,
        "ts": ts,
    })


async def broadcast_alert(level: str, code: str, detail: str, suggestion: str | None = None):
    """推送告警 (由 bridge._handle_alert 调用)。"""
    await broadcast({
        "type": "alert",
        "schema_version": SCHEMA_VERSION,
        "level": level,
        "code": code,
        "detail": detail,
        "suggestion": suggestion,
        "ts": time.time(),
    })


async def broadcast_status(flight_status: str, mode: str, current_action: int, total_actions: int, progress: int = 0):
    """推送任务状态 (progress 2026-08-05 新增: 前端 PROGRESS 进度条数据源)。"""
    await broadcast({
        "type": "status",
        "schema_version": SCHEMA_VERSION,
        "flightStatus": flight_status,
        "mode": mode,
        "currentAction": current_action,
        "totalActions": total_actions,
        "progress": progress,
        "ts": time.time(),
    })


async def broadcast_alpha_output(action: dict, goal: list | None, remaining: list):
    """推送 α 输出 (动作编码 + 目标点)。"""
    await broadcast({
        "type": "alpha_output",
        "schema_version": SCHEMA_VERSION,
        "action": action,
        "goal": goal,
        "remaining_actions": remaining,
        "ts": time.time(),
    })


async def broadcast_reject(reason: str, action_index: int, suggestion: str | None = None):
    """推送 reject (小模型/ego-planner 无法生成可达目标)。"""
    await broadcast({
        "type": "reject",
        "schema_version": SCHEMA_VERSION,
        "reason": reason,
        "actionIndex": action_index,
        "suggestedAction": suggestion,
        "ts": time.time(),
    })


async def broadcast_link_status(link: str, state: str, detail: str | None = None):
    """推送链路状态变更。"""
    await broadcast({
        "type": "link_status",
        "schema_version": SCHEMA_VERSION,
        "link": link,
        "state": state,
        "detail": detail,
        "ts": time.time(),
    })


async def broadcast_dashboard_config(panel_id: str, spec: dict, filter_spec: dict | None = None):
    """推送看板配置 (β dashboard_configure/dashboard_set_filter 工具驱动前端看板)。

    spec 与 filter 二选一或同给: configure 带 spec, set_filter 带 filter_spec。
    """
    await broadcast({
        "type": "dashboard_config",
        "schema_version": SCHEMA_VERSION,
        "panel_id": panel_id,
        "spec": spec,
        "filter": filter_spec,
        "ts": time.time(),
    })


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    """WebSocket 端点 — 双向实时通信。"""
    await ws.accept()
    await _add_client(ws)
    logger.info(f"[ws] client connected ({len(_clients)} total)")

    try:
        while True:
            raw = await ws.receive_text()
            # S2: 单消息限长
            if len(raw) > _WS_MSG_MAX:
                await ws.send_text(json.dumps({
                    "type": "error", "message": "message too large",
                }))
                continue
            # S2: 畸形 JSON 不回断, 回 error 帧
            try:
                msg = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                await ws.send_text(json.dumps({
                    "type": "error", "message": "invalid json",
                }))
                continue
            msg_type = msg.get("type", "")

            if msg_type == "sync":
                # 状态同步: 补齐当前位姿 + 飞行状态 + 当前会话 (#11: session_id 供前端恢复)
                s = _state_ref
                if s:
                    p = s.current_pose
                    await ws.send_text(json.dumps({
                        "type": "sync_response",
                        "session_id": s.session_id,
                        "current_pose": {
                            "pos": p.pos, "quat": p.quat, "vel": p.vel,
                        },
                        "flight_status": s.flight_status,
                        "ipc_connected": s.ipc_connected,
                        "pending_proposal": s.pending_proposal,
                    }))
            elif msg_type == "voice_frame":
                # 阶段 L 语音 (先导忽略)
                pass
            elif msg_type == "tts_request":
                # 阶段 L TTS (先导忽略)
                pass
            else:
                logger.debug(f"[ws] unknown message type: {msg_type}")

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"[ws] error: {e}")
    finally:
        await _remove_client(ws)
        logger.info(f"[ws] client disconnected ({len(_clients)} total)")
