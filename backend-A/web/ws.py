"""
WebSocket 处理 — 实时数据下行 (pose/status/reject/alert/alpha_output/...)。
接收前端 sync/voice_frame/tts_request, 推送飞行状态。
"""
import json
import time
import asyncio
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()

# 已连接前端列表
_connected: list[WebSocket] = []
_connected_lock = asyncio.Lock()

# 全局引用
_state_ref = None


def set_ws_context(state):
    global _state_ref
    _state_ref = state


async def broadcast(msg: dict):
    """向所有已连接前端推送消息。"""
    dead = []
    payload = json.dumps(msg, ensure_ascii=False)
    async with _connected_lock:
        for ws in _connected:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            if ws in _connected:
                _connected.remove(ws)


async def broadcast_pose(pos, quat, vel, accel, angular_vel, ts):
    """推送位姿 (10Hz, 由 bridge._handle_pose 调用)。"""
    await broadcast({
        "type": "pose",
        "schema_version": 2,
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
        "schema_version": 2,
        "level": level,
        "code": code,
        "detail": detail,
        "suggestion": suggestion,
        "ts": time.time(),
    })


async def broadcast_status(flight_status: str, mode: str, current_action: int, total_actions: int):
    """推送任务状态。"""
    await broadcast({
        "type": "status",
        "schema_version": 2,
        "flightStatus": flight_status,
        "mode": mode,
        "currentAction": current_action,
        "totalActions": total_actions,
        "ts": time.time(),
    })


async def broadcast_alpha_output(action: dict, goal: list | None, remaining: list):
    """推送 α 输出 (动作编码 + 目标点)。"""
    await broadcast({
        "type": "alpha_output",
        "schema_version": 2,
        "action": action,
        "goal": goal,
        "remaining_actions": remaining,
        "ts": time.time(),
    })


async def broadcast_reject(reason: str, action_index: int, suggestion: str | None = None):
    """推送 reject (小模型/ego-planner 无法生成可达目标)。"""
    await broadcast({
        "type": "reject",
        "schema_version": 2,
        "reason": reason,
        "actionIndex": action_index,
        "suggestedAction": suggestion,
        "ts": time.time(),
    })


async def broadcast_link_status(link: str, state: str, detail: str | None = None):
    """推送链路状态变更。"""
    await broadcast({
        "type": "link_status",
        "schema_version": 2,
        "link": link,
        "state": state,
        "detail": detail,
        "ts": time.time(),
    })


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    """WebSocket 端点 — 双向实时通信。"""
    await ws.accept()
    async with _connected_lock:
        _connected.append(ws)
    logger.info(f"[ws] client connected ({len(_connected)} total)")

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type", "")

            if msg_type == "sync":
                # 状态同步: 补齐当前位姿 + 飞行状态
                s = _state_ref
                if s:
                    p = s.current_pose
                    await ws.send_text(json.dumps({
                        "type": "sync_response",
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
        async with _connected_lock:
            if ws in _connected:
                _connected.remove(ws)
        logger.info(f"[ws] client disconnected ({len(_connected)} total)")
