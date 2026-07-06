"""Beta agent — central LLM scheduler (Lobster Mode).

Beta is the human-facing agent that:
1. Understands human flight intent
2. Schedules alpha translator and analytics tools
3. When receiving alerts, analyzes data and gives advice

Beta uses Pydantic AI with tool decorators for its 12 tools.
"""

from __future__ import annotations

import json
import logging
import time
from typing import AsyncGenerator, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from backend_A.state import AppState

logger = logging.getLogger(__name__)

SSE_CONTENT_TYPE = "text/event-stream"


async def run_beta(
    session_id: str,
    message: str,
    app_state: "AppState",
    beta_agent,
    db_session_factory,
    bus_router,
) -> AsyncGenerator[str, None]:
    """Run beta agent and yield SSE-formatted chunks.

    Yields SSE events:
    - text: streaming text deltas
    - tool_call_start: tool invocation started
    - tool_call_result: tool returned result
    - plan: FlightPlan proposal from beta
    - error: error occurred
    """
    # Store the human message for forward_last_human_message
    async with app_state.lock:
        app_state.last_human_message_to_beta = message

    # Build context with current state
    context = _build_context(app_state, session_id)

    try:
        async with beta_agent.run_stream(message, message_history=context) as stream:
            async for chunk in stream:
                event = _process_chunk(chunk, app_state, session_id)
                if event:
                    yield event

            # Get final output
            final = await stream.get_output()
            if final:
                _handle_beta_output(final, app_state, session_id)

    except Exception as exc:
        logger.error(f"agents/beta: run failed: {exc}", exc_info=True)
        yield f'data: {{"type":"error","message":"{str(exc)}"}}\n\n'


def _build_context(app_state: "AppState", session_id: str) -> list[dict]:
    """Build message context for beta with current state info."""
    context = []
    if app_state.current_pose:
        context.append({
            "role": "system",
            "content": (
                f"Current drone state: position={app_state.current_pose.get('pos')}, "
                f"velocity={app_state.current_pose.get('vel')}, "
                f"flight_status={app_state.flight_status}"
            ),
        })
    context.append({
        "role": "system",
        "content": f"Current session_id: {session_id}",
    })
    return context


def _process_chunk(chunk, app_state: "AppState", session_id: str) -> Optional[str]:
    """Process a streaming chunk from Pydantic AI and return SSE event string."""
    chunk_type = type(chunk).__name__

    # Text delta
    if chunk_type == "TextPartDelta" or (hasattr(chunk, "content") and isinstance(getattr(chunk, "content", None), str)):
        content = getattr(chunk, "content", str(chunk))
        return f'data: {{"type":"text","content":{json.dumps(content)}}}\n\n'

    # Tool call delta
    if chunk_type in ("ToolCallPartDelta", "ToolCallPart"):
        tool_name = getattr(chunk, "tool_name", "unknown")
        tool_args = getattr(chunk, "args", {})
        return f'data: {{"type":"tool_call_start","toolName":"{tool_name}","toolArgs":{json.dumps(tool_args)}}}\n\n'

    # Tool result
    if chunk_type in ("ToolReturnPart",):
        tool_name = getattr(chunk, "tool_name", "unknown")
        result = getattr(chunk, "content", "")
        return f'data: {{"type":"tool_call_result","toolName":"{tool_name}","result":{json.dumps(str(result))}}}\n\n'

    return None


def _handle_beta_output(output, app_state: "AppState", session_id: str) -> None:
    """Handle beta's final structured output (FlightPlan or other)."""
    if output is None:
        return
    # If output is a FlightPlan-like object, store as pending proposal
    if hasattr(output, "segments"):
        try:
            proposal = output.model_dump() if hasattr(output, "model_dump") else output
            async def _store():
                async with app_state.lock:
                    app_state.pending_proposal = {
                        "id": f"proposal_{int(time.time())}",
                        "intent": str(proposal),
                        "created_at": time.time(),
                        "session_id": session_id,
                        "plan": proposal,
                    }
            import asyncio
            asyncio.create_task(_store())
        except Exception as exc:
            logger.error(f"agents/beta: failed to store proposal: {exc}")
