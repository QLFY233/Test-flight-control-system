"""SSE streaming endpoint for beta chat."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend_A.db.session import get_session, AsyncSessionLocal
from backend_A.db.repos import ConversationRepo, run_agent_with_log
from backend_A.models.schemas import ChatRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# Runtime references
_app_state = None
_beta_agent = None
_bus_router = None
_sse_streams: set = set()

SSE_CONTENT_TYPE = "text/event-stream"


def init_sse(app_state, beta_agent, bus_router) -> None:
    global _app_state, _beta_agent, _bus_router
    _app_state = app_state
    _beta_agent = beta_agent
    _bus_router = bus_router


@router.post("/chat/beta")
async def chat_beta(req: ChatRequest):
    """SSE streaming chat with beta agent."""
    if _beta_agent is None:
        raise HTTPException(status_code=503, detail="Beta agent not initialized")

    # Store the human message for forward_last_human_message
    if _app_state:
        async with _app_state.lock:
            _app_state.last_human_message_to_beta = req.message

    # Log human message
    try:
        async with AsyncSessionLocal() as db:
            crepo = ConversationRepo(db)
            await crepo.add(req.session_id, "beta", "human", content=req.message)
    except Exception as exc:
        logger.error(f"SSE: failed to log human message: {exc}")

    stream_id = str(uuid.uuid4())[:8]

    async def event_stream():
        """Generate SSE events from beta agent."""
        try:
            from backend_A.agents.beta import run_beta

            async for sse_event in run_beta(
                session_id=req.session_id,
                message=req.message,
                app_state=_app_state,
                beta_agent=_beta_agent,
                db_session_factory=AsyncSessionLocal,
                bus_router=_bus_router,
            ):
                yield sse_event
        except Exception as exc:
            logger.error(f"SSE stream error: {exc}", exc_info=True)
            yield f'data: {{"type":"error","message":"{str(exc)}"}}\n\n'
        finally:
            yield "data: [DONE]\n\n"

        # Log agent response
        try:
            async with AsyncSessionLocal() as db:
                crepo = ConversationRepo(db)
                await crepo.add(
                    req.session_id, "beta", "agent",
                    content="[streaming response completed]",
                )
        except Exception:
            pass

    return StreamingResponse(
        event_stream(),
        media_type=SSE_CONTENT_TYPE,
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
