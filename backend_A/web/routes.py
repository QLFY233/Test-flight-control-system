"""REST API endpoints — 16 endpoints for sessions, history, environments, proposals, etc."""

from __future__ import annotations

import datetime
import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend_A.db.session import get_session, AsyncSessionLocal
from backend_A.db.repos import (
    SessionRepo,
    TelemetryRepo,
    ConversationRepo,
    EnvironmentRepo,
)
from backend_A.models.schemas import (
    SessionCreateRequest,
    SessionCreateResponse,
    SessionUpdateRequest,
    FlightSessionSummary,
    OverviewData,
    ProposalSummary,
    ProposalDetail,
    ProposalActionResponse,
    EnvData,
    EnvCreateRequest,
    FieldConfigResponse,
    CurrentPoseResponse,
    AbortResponse,
    TelemetryResponse,
    ErrorResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# AppState reference (set by main at startup)
_app_state = None
_config = None
_bus_router = None


def init_routes(app_state, config, bus_router) -> None:
    """Initialize routes with runtime references."""
    global _app_state, _config, _bus_router
    _app_state = app_state
    _config = config
    _bus_router = bus_router


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

@router.post("/sessions", response_model=SessionCreateResponse)
async def create_session(req: SessionCreateRequest, db: AsyncSession = Depends(get_session)):
    """Create a new flight session. Returns session_id in YYYYMMDDHHMMSS format."""
    repo = SessionRepo(db)
    now = datetime.datetime.utcnow()
    session_id = now.strftime("%Y%m%d%H%M%S")

    field_snapshot = None
    constraints_snapshot = None
    if _config:
        field_snapshot = _config.field.model_dump()
        constraints_snapshot = _config.constraints.model_dump()

    fs = await repo.create(
        session_id=session_id,
        name=req.name,
        environment_id=req.environment_id,
        field_snapshot=field_snapshot,
        constraints_snapshot=constraints_snapshot,
        notes=req.notes,
    )

    # Set as active session
    if _app_state:
        async with _app_state.lock:
            _app_state.session_id = session_id

    return SessionCreateResponse(
        session_id=fs.id,
        status=fs.status,
        created_at=fs.created_at,
    )


@router.get("/sessions/{session_id}", response_model=FlightSessionSummary)
async def get_session_info(session_id: str, db: AsyncSession = Depends(get_session)):
    """Get session details."""
    repo = SessionRepo(db)
    fs = await repo.get(session_id)
    if fs is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return FlightSessionSummary(
        id=fs.id, name=fs.name, status=fs.status,
        created_at=fs.created_at, started_at=fs.started_at,
        ended_at=fs.ended_at, environment_id=fs.environment_id,
        notes=fs.notes,
    )


@router.patch("/sessions/{session_id}", response_model=FlightSessionSummary)
async def update_session(
    session_id: str, req: SessionUpdateRequest, db: AsyncSession = Depends(get_session)
):
    """Update a session (start, end, rename, etc.)."""
    repo = SessionRepo(db)
    updates = {k: v for k, v in req.model_dump(exclude_none=True).items()}
    if req.status == "active":
        fs = await repo.start(session_id)
    elif req.status == "completed":
        fs = await repo.complete(session_id)
    elif req.status == "aborted":
        fs = await repo.abort(session_id)
    else:
        fs = await repo.update(session_id, **updates)

    if fs is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return FlightSessionSummary(
        id=fs.id, name=fs.name, status=fs.status,
        created_at=fs.created_at, started_at=fs.started_at,
        ended_at=fs.ended_at, environment_id=fs.environment_id,
        notes=fs.notes,
    )


@router.post("/sessions/{session_id}/abort", response_model=AbortResponse)
async def abort_session(session_id: str, db: AsyncSession = Depends(get_session)):
    """Emergency abort: clear trajectory, send abort to B, mark session aborted."""
    repo = SessionRepo(db)
    fs = await repo.get(session_id)
    if fs is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # Clear alpha state
    if _app_state:
        async with _app_state.lock:
            _app_state.alpha_input_queue.clear()
            _app_state.current_trajectory_plan = None
            _app_state.pending_proposal = None
            _app_state.flight_status = "aborted"

    # Send abort to B via bus
    if _bus_router:
        try:
            await _bus_router.call(to="solver", tool="abort", args={})
        except Exception as exc:
            logger.error(f"abort_session: failed to send abort to B: {exc}")

    # Mark session aborted
    await repo.abort(session_id)

    return AbortResponse(status="aborted", message="Flight aborted successfully")


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------

@router.get("/overview", response_model=OverviewData)
async def get_overview(db: AsyncSession = Depends(get_session)):
    """System overview: status, recent sessions, environment."""
    now = time.time()

    # Backend B: check pong timestamp
    if _app_state:
        last_pong = _app_state.last_pong_at
        backend_b = "ok" if (now - last_pong) < 5.0 else "down"
        drone = "online" if (now - _app_state.pose_updated_at) < 1.0 else "offline"
        llm_status = "ok" if _app_state.last_llm_call_ok else "error"
        flight_status = _app_state.flight_status
        active_session = _app_state.session_id
        has_pending = _app_state.pending_proposal is not None
    else:
        backend_b = "unknown"
        drone = "unknown"
        llm_status = "ok"
        flight_status = "idle"
        active_session = None
        has_pending = False

    # Recent sessions
    srepo = SessionRepo(db)
    recent = await srepo.list_all(limit=6)

    return OverviewData(
        backend_a="ok",
        backend_b=backend_b,
        drone=drone,
        llm=llm_status,
        flight_status=flight_status,
        active_session_id=active_session,
        pending_proposal=has_pending,
        recent_sessions=[
            FlightSessionSummary(
                id=s.id, name=s.name, status=s.status,
                created_at=s.created_at, started_at=s.started_at,
                ended_at=s.ended_at, environment_id=s.environment_id,
                notes=s.notes,
            )
            for s in recent
        ],
    )


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

@router.get("/history/sessions")
async def list_history_sessions(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_session),
):
    """List historical flight sessions."""
    srepo = SessionRepo(db)
    sessions = await srepo.list_all(limit=limit, offset=offset, status=status)
    total = await srepo.count(status=status)
    return {
        "sessions": [
            FlightSessionSummary(
                id=s.id, name=s.name, status=s.status,
                created_at=s.created_at, started_at=s.started_at,
                ended_at=s.ended_at, environment_id=s.environment_id,
                notes=s.notes,
            ).model_dump()
            for s in sessions
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/history/telemetry/{session_id}", response_model=TelemetryResponse)
async def get_history_telemetry(
    session_id: str,
    t_min: float = Query(0),
    t_max: float = Query(0),
    limit: int = Query(10000, ge=1, le=100000),
    db: AsyncSession = Depends(get_session),
):
    """Get telemetry time series for a session."""
    trepo = TelemetryRepo(db)
    tmin = t_min if t_min > 0 else None
    tmax = t_max if t_max > 0 else None
    points = await trepo.query_by_session(session_id, t_min=tmin, t_max=tmax, limit=limit)
    return TelemetryResponse(
        session_id=session_id,
        count=len(points),
        points=[
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
    )


@router.get("/history/conversations/{session_id}")
async def get_history_conversations(
    session_id: str,
    agent: str = Query(""),
    limit: int = Query(200, ge=1, le=2000),
    db: AsyncSession = Depends(get_session),
):
    """Get conversation history for a session."""
    crepo = ConversationRepo(db)
    if agent:
        convs = await crepo.load_recent(session_id, agent, limit)
    else:
        convs = await crepo.load_all(session_id)
    return {
        "session_id": session_id,
        "count": len(convs),
        "conversations": [
            {
                "id": c.id,
                "agent": c.agent,
                "role": c.role,
                "content": c.content,
                "metadata": c.metadata_,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in convs[:limit]
        ],
    }


# ---------------------------------------------------------------------------
# Environments
# ---------------------------------------------------------------------------

@router.get("/environments")
async def list_environments(db: AsyncSession = Depends(get_session)):
    """List all environment presets."""
    erepo = EnvironmentRepo(db)
    envs = await erepo.list_all()
    return {
        "environments": [
            EnvData(
                id=e.id, name=e.name, description=e.description,
                data=e.data, created_at=e.created_at, updated_at=e.updated_at,
            ).model_dump()
            for e in envs
        ]
    }


@router.get("/environments/{env_id}")
async def get_environment(env_id: int, db: AsyncSession = Depends(get_session)):
    """Get a single environment by ID."""
    erepo = EnvironmentRepo(db)
    env = await erepo.get(env_id)
    if env is None:
        raise HTTPException(status_code=404, detail="Environment not found")
    return EnvData(
        id=env.id, name=env.name, description=env.description,
        data=env.data, created_at=env.created_at, updated_at=env.updated_at,
    )


@router.post("/environments", response_model=EnvData)
async def create_environment(req: EnvCreateRequest, db: AsyncSession = Depends(get_session)):
    """Create or update an environment preset."""
    erepo = EnvironmentRepo(db)
    env = await erepo.upsert(name=req.name, data=req.data, description=req.description)
    return EnvData(
        id=env.id, name=env.name, description=env.description,
        data=env.data, created_at=env.created_at, updated_at=env.updated_at,
    )


# ---------------------------------------------------------------------------
# Field Config
# ---------------------------------------------------------------------------

@router.get("/field/config", response_model=FieldConfigResponse)
async def get_field_config():
    """Get current field configuration (boundary, home, obstacles)."""
    if _config is None:
        raise HTTPException(status_code=500, detail="Config not loaded")
    return FieldConfigResponse(
        boundary=_config.field.boundary.model_dump(),
        home=_config.field.home.model_dump(),
        obstacles=[o.model_dump() for o in _config.field.obstacles],
    )


# ---------------------------------------------------------------------------
# Proposals (beta's proposed plans for human review)
# ---------------------------------------------------------------------------

@router.get("/proposals")
async def list_proposals():
    """List pending beta proposals."""
    if _app_state is None:
        return {"proposals": []}
    async with _app_state.lock:
        p = _app_state.pending_proposal
    if p is None:
        return {"proposals": []}
    return {
        "proposals": [
            ProposalSummary(
                id=p["id"],
                intent=p.get("intent", ""),
                created_at=p.get("created_at", 0),
                session_id=p.get("session_id"),
            ).model_dump()
        ]
    }


@router.get("/proposals/{proposal_id}", response_model=ProposalDetail)
async def get_proposal(proposal_id: str):
    """Get a specific proposal by ID."""
    if _app_state is None:
        raise HTTPException(status_code=404, detail="No app state")
    async with _app_state.lock:
        p = _app_state.pending_proposal
    if p is None or p["id"] != proposal_id:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return ProposalDetail(
        id=p["id"],
        intent=p.get("intent", ""),
        plan=p.get("plan"),
        created_at=p.get("created_at", 0),
        session_id=p.get("session_id"),
    )


@router.post("/proposals/{proposal_id}/approve", response_model=ProposalActionResponse)
async def approve_proposal(proposal_id: str):
    """Approve a beta proposal — inject into alpha queue."""
    if _app_state is None:
        raise HTTPException(status_code=500, detail="No app state")
    async with _app_state.lock:
        p = _app_state.pending_proposal
        if p is None or p["id"] != proposal_id:
            raise HTTPException(status_code=404, detail="Proposal not found")
        intent = p.get("intent", "")
        _app_state.add_alpha_input(f"[approved] {intent}")
        _app_state.pending_proposal = None

    # Log approval
    try:
        async with AsyncSessionLocal() as db:
            crepo = ConversationRepo(db)
            await crepo.add(
                _app_state.session_id or "unknown",
                "alpha", "tool_call",
                content=f"approved proposal: {intent}",
                metadata={"path": "propose", "approved": True, "proposal_id": proposal_id},
            )
    except Exception as exc:
        logger.error(f"approve_proposal: log failed: {exc}")

    return ProposalActionResponse(
        status="approved", message="Proposal approved, sent to alpha",
        proposal_id=proposal_id,
    )


@router.post("/proposals/{proposal_id}/reject", response_model=ProposalActionResponse)
async def reject_proposal(proposal_id: str):
    """Reject a beta proposal."""
    if _app_state is None:
        raise HTTPException(status_code=500, detail="No app state")
    async with _app_state.lock:
        p = _app_state.pending_proposal
        if p is None or p["id"] != proposal_id:
            raise HTTPException(status_code=404, detail="Proposal not found")
        _app_state.pending_proposal = None

    return ProposalActionResponse(
        status="rejected", message="Proposal rejected",
        proposal_id=proposal_id,
    )


# ---------------------------------------------------------------------------
# Current Pose
# ---------------------------------------------------------------------------

@router.get("/current-pose", response_model=CurrentPoseResponse)
async def get_current_pose():
    """Get current drone pose (one-shot, non-streaming)."""
    if _app_state is None:
        return CurrentPoseResponse()
    async with _app_state.lock:
        pose = _app_state.current_pose
        flight_status = _app_state.flight_status
    if pose is None:
        return CurrentPoseResponse(flight_status=flight_status)
    return CurrentPoseResponse(
        pos=pose.get("pos"),
        quat=pose.get("quat"),
        vel=pose.get("vel"),
        ts=pose.get("ts", 0),
        flight_status=flight_status,
    )
