"""Pydantic request/response models for REST API and WebSocket messages."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    session_id: str
    message: str
    auto_send: bool = False


# ---------------------------------------------------------------------------
# Flight Session
# ---------------------------------------------------------------------------

class SessionCreateRequest(BaseModel):
    name: Optional[str] = None
    environment_id: Optional[int] = None
    notes: Optional[str] = None


class SessionCreateResponse(BaseModel):
    session_id: str
    status: str
    created_at: Optional[datetime] = None


class SessionUpdateRequest(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class FlightSessionSummary(BaseModel):
    id: str
    name: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    environment_id: Optional[int] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------

class OverviewData(BaseModel):
    backend_a: str = "ok"
    backend_b: str = "unknown"
    drone: str = "unknown"
    llm: str = "ok"
    flight_status: str = "idle"
    active_session_id: Optional[str] = None
    pending_proposal: bool = False
    recent_sessions: list[FlightSessionSummary] = Field(default_factory=list)
    environment: Optional[dict] = None


# ---------------------------------------------------------------------------
# Proposals
# ---------------------------------------------------------------------------

class ProposalSummary(BaseModel):
    id: str
    intent: str
    created_at: float
    session_id: Optional[str] = None
    status: str = "pending"


class ProposalDetail(BaseModel):
    id: str
    intent: str
    plan: Optional[dict] = None
    created_at: float
    session_id: Optional[str] = None
    status: str = "pending"


class ProposalActionResponse(BaseModel):
    status: str
    message: str
    proposal_id: str


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

class EnvData(BaseModel):
    id: Optional[int] = None
    name: str
    description: Optional[str] = None
    data: dict = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class EnvCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    data: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------

class TelemetryPoint(BaseModel):
    t: float
    pos: Optional[list[float]] = None  # [x, y, z]
    quat: Optional[list[float]] = None  # [w, x, y, z]
    vel: Optional[list[float]] = None  # [vx, vy, vz]
    accel: Optional[list[float]] = None
    angular_vel: Optional[list[float]] = None


class TelemetryResponse(BaseModel):
    session_id: str
    count: int
    points: list[dict]


# ---------------------------------------------------------------------------
# Trajectory / Flight Plan
# ---------------------------------------------------------------------------

class FlightPlanSegment(BaseModel):
    id: str = ""
    type: str = "waypoint"
    waypoints: list[dict] = Field(default_factory=list)
    speed: float = 1.0
    acceleration: float = 1.0
    duration: float = 0.0
    description: str = ""


class FlightPlan(BaseModel):
    task_id: str = ""
    segments: list[FlightPlanSegment] = Field(default_factory=list)
    constraints: dict = Field(default_factory=dict)
    summary: Optional[str] = None


class FieldConfigResponse(BaseModel):
    boundary: dict
    home: dict
    obstacles: list[dict]


class CurrentPoseResponse(BaseModel):
    pos: Optional[list[float]] = None
    quat: Optional[list[float]] = None
    vel: Optional[list[float]] = None
    ts: float = 0.0
    flight_status: str = "idle"


class AbortResponse(BaseModel):
    status: str
    message: str = "Flight aborted"


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
