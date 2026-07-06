"""SQLAlchemy ORM models — 4 tables.

Tables:
- environments: environmental condition presets
- flight_sessions: each flight session
- telemetry: high-frequency sensor data (UNIQUE(session_id, t))
- conversations: agent interaction log (agent, role, content, metadata)
"""

from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import (
    Column,
    Float,
    Integer,
    String,
    Text,
    DateTime,
    JSON,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Environment(Base):
    __tablename__ = "environments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # data contains: { temperature, humidity, wind_speed, wind_direction, pressure, ... }
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<Environment id={self.id} name={self.name!r}>"


class FlightSession(Base):
    __tablename__ = "flight_sessions"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    # id format: YYYYMMDDHHMMSS (also serves as task_id)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="created"
    )
    # status: created / active / completed / aborted
    environment_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    field_config_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    constraints_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )
    started_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<FlightSession id={self.id} status={self.status!r}>"


class Telemetry(Base):
    __tablename__ = "telemetry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    t: Mapped[float] = mapped_column(Float, nullable=False)
    # Position
    pos_x: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pos_y: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pos_z: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Quaternion (w, x, y, z)
    quat_w: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quat_x: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quat_y: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quat_z: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Velocity
    vel_x: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    vel_y: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    vel_z: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Acceleration
    accel_x: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    accel_y: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    accel_z: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Angular velocity
    angular_velocity_x: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    angular_velocity_y: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    angular_velocity_z: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Raw telemetry metadata (optional)
    extra: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )

    __table_args__ = (
        UniqueConstraint("session_id", "t", name="uq_telemetry_session_t"),
        Index("idx_telemetry_session_t", "session_id", "t"),
    )

    def __repr__(self) -> str:
        return f"<Telemetry session={self.session_id} t={self.t}>"


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    agent: Mapped[str] = mapped_column(String(32), nullable=False)
    # agent: "alpha" | "beta" | "human" | "system"
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    # role: "human" | "agent" | "tool_call" | "tool_result" | "system"
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSON, nullable=True)
    # metadata for alpha: { "approved": bool, "path": "propose"|"forward", "proposal_id": ... }
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )

    __table_args__ = (
        Index("idx_conversations_session_agent", "session_id", "agent"),
    )

    def __repr__(self) -> str:
        return f"<Conversation session={self.session_id} agent={self.agent} role={self.role}>"
