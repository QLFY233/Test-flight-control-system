"""Beta's 12 tool functions — history query, real-time status, alpha dispatch, analytics.

All tools are Pydantic AI-compatible async functions that beta can call.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from backend_A.state import AppState

logger = logging.getLogger(__name__)

# References set at startup
_app_state: Optional["AppState"] = None
_db_session_factory = None
_bus_router = None
_config = None


def init_tools(app_state: "AppState", db_factory, bus_router, config) -> None:
    """Initialize tool module with runtime dependencies."""
    global _app_state, _db_session_factory, _bus_router, _config
    _app_state = app_state
    _db_session_factory = db_factory
    _bus_router = bus_router
    _config = config


# ---------------------------------------------------------------------------
# History / Status tools
# ---------------------------------------------------------------------------

async def get_field_map() -> dict:
    """Return the current field configuration (boundary, obstacles, home)."""
    if _config is None:
        return {"error": "config not loaded"}
    return {
        "boundary": _config.field.boundary.model_dump(),
        "home": _config.field.home.model_dump(),
        "obstacles": [o.model_dump() for o in _config.field.obstacles],
    }


async def get_current_pose() -> dict:
    """Get the latest drone pose from AppState cache."""
    if _app_state is None:
        return {"error": "app state not available"}
    async with _app_state.lock:
        pose = _app_state.current_pose
    if pose is None:
        return {"pos": [0, 0, 0], "quat": [1, 0, 0, 0], "vel": [0, 0, 0], "ts": 0}
    return dict(pose)


async def get_recent_telemetry(window_sec: float = 10.0) -> dict:
    """Get recent telemetry data for the current session."""
    if _app_state is None or _app_state.session_id is None:
        return {"error": "no active session"}
    try:
        async with _db_session_factory() as db:
            from backend_A.db.repos import TelemetryRepo
            repo = TelemetryRepo(db)
            points = await repo.recent(_app_state.session_id, window_sec)
            return {
                "session_id": _app_state.session_id,
                "count": len(points),
                "points": [
                    {
                        "t": p.t,
                        "pos": [p.pos_x, p.pos_y, p.pos_z],
                        "vel": [p.vel_x, p.vel_y, p.vel_z],
                    }
                    for p in points[:100]  # limit for context window
                ],
            }
    except Exception as exc:
        return {"error": str(exc)}


async def get_current_environment() -> dict:
    """Get the current session's environment data."""
    if _app_state is None or _app_state.session_id is None:
        return {"environment": None, "note": "no active session"}
    try:
        async with _db_session_factory() as db:
            from backend_A.db.repos import SessionRepo, EnvironmentRepo
            srepo = SessionRepo(db)
            fs = await srepo.get(_app_state.session_id)
            if fs is None or fs.environment_id is None:
                return {"environment": None, "note": "no environment set"}
            erepo = EnvironmentRepo(db)
            env = await erepo.get(fs.environment_id)
            if env is None:
                return {"environment": None}
            return {
                "environment": {
                    "id": env.id,
                    "name": env.name,
                    "data": env.data,
                }
            }
    except Exception as exc:
        return {"error": str(exc)}


async def query_sessions(limit: int = 20, status: str = "") -> dict:
    """Query historical flight sessions."""
    try:
        async with _db_session_factory() as db:
            from backend_A.db.repos import SessionRepo
            repo = SessionRepo(db)
            s = status if status else None
            sessions = await repo.list_all(limit=limit, status=s)
            return {
                "sessions": [
                    {
                        "id": fs.id,
                        "name": fs.name,
                        "status": fs.status,
                        "created_at": fs.created_at.isoformat() if fs.created_at else None,
                    }
                    for fs in sessions
                ],
                "count": len(sessions),
            }
    except Exception as exc:
        return {"error": str(exc)}


async def query_telemetry(session_id: str, t_min: float = 0, t_max: float = 0, limit: int = 1000) -> dict:
    """Query telemetry for a specific session."""
    try:
        async with _db_session_factory() as db:
            from backend_A.db.repos import TelemetryRepo
            repo = TelemetryRepo(db)
            tmin = t_min if t_min > 0 else None
            tmax = t_max if t_max > 0 else None
            points = await repo.query_by_session(session_id, t_min=tmin, t_max=tmax, limit=limit)
            return {
                "session_id": session_id,
                "count": len(points),
                "points": [
                    {
                        "t": p.t,
                        "pos": [p.pos_x, p.pos_y, p.pos_z],
                        "quat": [p.quat_w, p.quat_x, p.quat_y, p.quat_z],
                        "vel": [p.vel_x, p.vel_y, p.vel_z],
                        "accel": [p.accel_x, p.accel_y, p.accel_z],
                        "angularVel": [p.angular_velocity_x, p.angular_velocity_y, p.angular_velocity_z],
                    }
                    for p in points
                ],
            }
    except Exception as exc:
        return {"error": str(exc)}


async def query_environment(env_id: int = 0) -> dict:
    """Query environment by ID, or list all."""
    try:
        async with _db_session_factory() as db:
            from backend_A.db.repos import EnvironmentRepo
            repo = EnvironmentRepo(db)
            if env_id > 0:
                env = await repo.get(env_id)
                if env is None:
                    return {"error": f"environment {env_id} not found"}
                return {"environment": {"id": env.id, "name": env.name, "data": env.data}}
            else:
                envs = await repo.list_all()
                return {
                    "environments": [
                        {"id": e.id, "name": e.name, "data": e.data} for e in envs
                    ]
                }
    except Exception as exc:
        return {"error": str(exc)}


async def query_conversations(session_id: str, agent: str = "", limit: int = 50) -> dict:
    """Query conversation history for a session."""
    try:
        async with _db_session_factory() as db:
            from backend_A.db.repos import ConversationRepo
            repo = ConversationRepo(db)
            if agent:
                convs = await repo.load_recent(session_id, agent, limit)
            else:
                convs = await repo.load_all(session_id)
            return {
                "session_id": session_id,
                "count": len(convs),
                "conversations": [
                    {
                        "id": c.id,
                        "agent": c.agent,
                        "role": c.role,
                        "content": c.content[:500] if c.content else None,
                        "created_at": c.created_at.isoformat() if c.created_at else None,
                    }
                    for c in convs[:limit]
                ],
            }
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Alpha dispatch tools
# ---------------------------------------------------------------------------

async def propose_to_alpha(intent: str) -> dict:
    """Propose an intent to alpha — REQUIRES HUMAN APPROVAL.

    The intent is stored as pending_proposal. Frontend shows it for human review.
    Only after human confirms does the intent enter alpha_input_queue.
    """
    if _app_state is None:
        return {"error": "app state not available"}

    proposal_id = f"proposal_{int(time.time())}"
    proposal = {
        "id": proposal_id,
        "intent": intent,
        "created_at": time.time(),
        "session_id": _app_state.session_id,
    }

    async with _app_state.lock:
        _app_state.pending_proposal = proposal

    logger.info(f"tools: propose_to_alpha stored proposal {proposal_id}")
    return {
        "status": "pending_approval",
        "proposal_id": proposal_id,
        "intent": intent,
        "message": "Proposal stored. Human approval required before alpha executes.",
    }


async def forward_last_human_message() -> dict:
    """Forward the last human message directly to alpha — NO approval needed.

    The human already spoke, so this is just routing their words to alpha.
    """
    if _app_state is None:
        return {"error": "app state not available"}

    async with _app_state.lock:
        msg = _app_state.last_human_message_to_beta

    if msg is None:
        return {"status": "no_message", "message": "No recent human message to forward."}

    async with _app_state.lock:
        _app_state.add_alpha_input(msg)

    # Log the forward as conversation
    try:
        async with _db_session_factory() as db:
            from backend_A.db.repos import ConversationRepo
            repo = ConversationRepo(db)
            await repo.add(
                _app_state.session_id or "unknown",
                "alpha",
                "tool_call",
                content=f"forward: {msg}",
                metadata={"path": "forward", "approved": True},
            )
    except Exception as exc:
        logger.error(f"forward_last_human_message: log failed: {exc}")

    return {
        "status": "forwarded",
        "message": "Human message forwarded to alpha for translation.",
    }


# ---------------------------------------------------------------------------
# Analytics tools
# ---------------------------------------------------------------------------

async def analytics_fft(data: list[float], sampling_rate: float = 10.0) -> dict:
    """Run FFT analysis on a time series."""
    try:
        from backend_A.analytics.fft import FFTTool
        tool = FFTTool()
        result = tool.analyze(data, {"sampling_rate": sampling_rate})
        return {"tool": "fft", "result": result}
    except Exception as exc:
        return {"error": str(exc)}


async def analytics_stats(data: list[float]) -> dict:
    """Run statistical analysis (mean, variance, extrema, trend)."""
    try:
        from backend_A.analytics.stats import StatsTool
        tool = StatsTool()
        result = tool.analyze(data, {})
        return {"tool": "stats", "result": result}
    except Exception as exc:
        return {"error": str(exc)}


async def analytics_filter(
    data: list[float],
    filter_type: str = "lowpass",
    cutoff: float = 0.2,
    window_size: int = 5,
) -> dict:
    """Apply a filter to a time series."""
    try:
        from backend_A.analytics.filter import FilterTool
        tool = FilterTool()
        params = {"filter_type": filter_type, "cutoff": cutoff, "window_size": window_size}
        result = tool.analyze(data, params)
        return {"tool": "filter", "filter_type": filter_type, "result": result}
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Collect all tool functions for beta agent registration
# ---------------------------------------------------------------------------

def get_all_tools() -> list:
    """Return all tool functions for registration with beta agent."""
    return [
        get_field_map,
        get_current_pose,
        get_recent_telemetry,
        get_current_environment,
        query_sessions,
        query_telemetry,
        query_environment,
        query_conversations,
        propose_to_alpha,
        forward_last_human_message,
        analytics_fft,
        analytics_stats,
        analytics_filter,
    ]
