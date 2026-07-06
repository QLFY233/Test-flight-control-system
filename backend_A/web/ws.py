"""WebSocket handler — upstream voice/tts/sync, downstream pose/status/alert/alpha_output."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()

# Runtime references
_app_state = None
_bus_router = None


def init_ws(app_state, bus_router) -> None:
    global _app_state, _bus_router
    _app_state = app_state
    _bus_router = bus_router


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Main WebSocket endpoint for frontend communication."""
    await websocket.accept()

    # Register connection
    if _app_state:
        async with _app_state.lock:
            _app_state.ws_connections.add(websocket)

    logger.info(f"WS: client connected (total: {len(_app_state.ws_connections) if _app_state else 0})")

    # Send initial link status
    if _app_state:
        await _send_json(websocket, {
            "type": "link_status",
            "schema_version": 1,
            "link": "A-B",
            "state": "up" if _app_state.ipc_connected else "down",
        })

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning(f"WS: invalid JSON: {raw[:100]}")
                continue

            msg_type = msg.get("type", "")
            await _handle_upstream(websocket, msg_type, msg)

    except WebSocketDisconnect:
        logger.info("WS: client disconnected")
    except Exception as exc:
        logger.error(f"WS: error: {exc}", exc_info=True)
    finally:
        # Unregister
        if _app_state:
            async with _app_state.lock:
                _app_state.ws_connections.discard(websocket)


async def _handle_upstream(ws: WebSocket, msg_type: str, msg: dict) -> None:
    """Process incoming WebSocket messages from frontend."""
    if msg_type == "sync":
        # State sync — return current pose + status
        response = {"type": "sync_response", "schema_version": 1}
        if _app_state:
            async with _app_state.lock:
                pose = _app_state.current_pose
                response["status"] = _app_state.flight_status
                if pose:
                    response["pose"] = pose.get("pos")
                    response["quat"] = pose.get("quat")
        await _send_json(ws, response)

    elif msg_type == "voice_frame":
        # STT audio frame — forward to speech module
        data = msg.get("data", "")
        seq = msg.get("seq", 0)
        auto_send = msg.get("auto_send", False)

        # Stub: return placeholder STT result
        try:
            from backend_A.speech.stt_client import process_voice_frame
            result = await process_voice_frame(data, seq, _app_state)
            if result:
                await _send_json(ws, {
                    "type": "voice_stt_result",
                    "schema_version": 1,
                    "text": result.get("text", ""),
                    "is_final": result.get("is_final", False),
                })
        except Exception as exc:
            logger.error(f"WS: STT error: {exc}")

    elif msg_type == "tts_request":
        # TTS synthesis request
        text = msg.get("text", "")
        try:
            from backend_A.speech.tts_client import synthesize
            audio_data = await synthesize(text)
            if audio_data:
                await _send_json(ws, {
                    "type": "voice_tts",
                    "schema_version": 1,
                    "data": audio_data,
                    "format": "mp3",
                })
        except Exception as exc:
            logger.error(f"WS: TTS error: {exc}")

    else:
        logger.debug(f"WS: unhandled message type: {msg_type}")


async def _send_json(ws: WebSocket, msg: dict) -> None:
    """Send a JSON message over WebSocket."""
    try:
        await ws.send_text(json.dumps(msg, ensure_ascii=False))
    except Exception:
        pass
