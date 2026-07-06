"""Repository classes for database CRUD operations."""

from __future__ import annotations

import datetime
import json
import logging
import time
from typing import Optional, AsyncGenerator

from sqlalchemy import select, func, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend_A.db.models import (
    Environment,
    FlightSession,
    Telemetry,
    Conversation,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# EnvironmentRepo
# ---------------------------------------------------------------------------

class EnvironmentRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, name: str, description: str | None, data: dict) -> Environment:
        env = Environment(name=name, description=description, data=data)
        self.session.add(env)
        await self.session.commit()
        await self.session.refresh(env)
        return env

    async def get(self, env_id: int) -> Optional[Environment]:
        return await self.session.get(Environment, env_id)

    async def list_all(self) -> list[Environment]:
        result = await self.session.execute(
            select(Environment).order_by(Environment.created_at.desc())
        )
        return list(result.scalars().all())

    async def update(self, env_id: int, **kwargs) -> Optional[Environment]:
        env = await self.get(env_id)
        if env is None:
            return None
        for k, v in kwargs.items():
            if hasattr(env, k):
                setattr(env, k, v)
        env.updated_at = datetime.datetime.utcnow()
        await self.session.commit()
        return env

    async def upsert(self, name: str, data: dict, description: str | None = None) -> Environment:
        """Create or update an environment by name."""
        result = await self.session.execute(
            select(Environment).where(Environment.name == name)
        )
        env = result.scalar_one_or_none()
        if env:
            env.data = data
            if description is not None:
                env.description = description
            env.updated_at = datetime.datetime.utcnow()
        else:
            env = Environment(name=name, description=description, data=data)
            self.session.add(env)
        await self.session.commit()
        await self.session.refresh(env)
        return env


# ---------------------------------------------------------------------------
# SessionRepo
# ---------------------------------------------------------------------------

class SessionRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        session_id: str,
        name: str | None = None,
        environment_id: int | None = None,
        field_snapshot: dict | None = None,
        constraints_snapshot: dict | None = None,
        notes: str | None = None,
    ) -> FlightSession:
        fs = FlightSession(
            id=session_id,
            name=name,
            status="created",
            environment_id=environment_id,
            field_config_snapshot=field_snapshot,
            constraints_snapshot=constraints_snapshot,
            notes=notes,
        )
        self.session.add(fs)
        await self.session.commit()
        await self.session.refresh(fs)
        return fs

    async def get(self, session_id: str) -> Optional[FlightSession]:
        return await self.session.get(FlightSession, session_id)

    async def update(self, session_id: str, **kwargs) -> Optional[FlightSession]:
        fs = await self.get(session_id)
        if fs is None:
            return None
        for k, v in kwargs.items():
            if hasattr(fs, k):
                setattr(fs, k, v)
        await self.session.commit()
        return fs

    async def start(self, session_id: str) -> Optional[FlightSession]:
        return await self.update(
            session_id, status="active", started_at=datetime.datetime.utcnow()
        )

    async def complete(self, session_id: str) -> Optional[FlightSession]:
        return await self.update(
            session_id, status="completed", ended_at=datetime.datetime.utcnow()
        )

    async def abort(self, session_id: str) -> Optional[FlightSession]:
        return await self.update(
            session_id, status="aborted", ended_at=datetime.datetime.utcnow()
        )

    async def list_all(
        self, limit: int = 50, offset: int = 0, status: str | None = None
    ) -> list[FlightSession]:
        stmt = select(FlightSession).order_by(FlightSession.created_at.desc())
        if status:
            stmt = stmt.where(FlightSession.status == status)
        stmt = stmt.limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count(self, status: str | None = None) -> int:
        stmt = select(func.count(FlightSession.id))
        if status:
            stmt = stmt.where(FlightSession.status == status)
        result = await self.session.execute(stmt)
        return result.scalar_one()


# ---------------------------------------------------------------------------
# TelemetryRepo
# ---------------------------------------------------------------------------

class TelemetryRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert(self, session_id: str, point: dict) -> Telemetry:
        """Insert a single telemetry point."""
        t = Telemetry(
            session_id=session_id,
            t=point.get("ts", time.time()),
            pos_x=point.get("pos", [None, None, None])[0],
            pos_y=point.get("pos", [None, None, None])[1],
            pos_z=point.get("pos", [None, None, None])[2],
            quat_w=point.get("quat", [None, None, None, None])[0],
            quat_x=point.get("quat", [None, None, None, None])[1],
            quat_y=point.get("quat", [None, None, None, None])[2],
            quat_z=point.get("quat", [None, None, None, None])[3],
            vel_x=point.get("vel", [None, None, None])[0],
            vel_y=point.get("vel", [None, None, None])[1],
            vel_z=point.get("vel", [None, None, None])[2],
            accel_x=point.get("accel", [None, None, None])[0],
            accel_y=point.get("accel", [None, None, None])[1],
            accel_z=point.get("accel", [None, None, None])[2],
            angular_velocity_x=point.get("angularVel", [None, None, None])[0],
            angular_velocity_y=point.get("angularVel", [None, None, None])[1],
            angular_velocity_z=point.get("angularVel", [None, None, None])[2],
            extra=point.get("extra"),
        )
        self.session.add(t)
        await self.session.commit()
        return t

    async def batch_insert(self, session_id: str, points: list[dict]) -> int:
        """Batch insert telemetry points."""
        count = 0
        for point in points:
            try:
                t = Telemetry(
                    session_id=session_id,
                    t=point.get("ts", time.time()),
                    pos_x=point.get("pos", [None, None, None])[0],
                    pos_y=point.get("pos", [None, None, None])[1],
                    pos_z=point.get("pos", [None, None, None])[2],
                    quat_w=point.get("quat", [None, None, None, None])[0],
                    quat_x=point.get("quat", [None, None, None, None])[1],
                    quat_y=point.get("quat", [None, None, None, None])[2],
                    quat_z=point.get("quat", [None, None, None, None])[3],
                    vel_x=point.get("vel", [None, None, None])[0],
                    vel_y=point.get("vel", [None, None, None])[1],
                    vel_z=point.get("vel", [None, None, None])[2],
                    accel_x=point.get("accel", [None, None, None])[0] if point.get("accel") else None,
                    accel_y=point.get("accel", [None, None, None])[1] if point.get("accel") else None,
                    accel_z=point.get("accel", [None, None, None])[2] if point.get("accel") else None,
                    angular_velocity_x=point.get("angularVel", [None, None, None])[0] if point.get("angularVel") else None,
                    angular_velocity_y=point.get("angularVel", [None, None, None])[1] if point.get("angularVel") else None,
                    angular_velocity_z=point.get("angularVel", [None, None, None])[2] if point.get("angularVel") else None,
                    extra=point.get("extra"),
                )
                self.session.add(t)
                count += 1
            except Exception as exc:
                logger.warning(f"batch_insert: skipping point due to {exc}")
        await self.session.commit()
        return count

    async def query_by_session(
        self,
        session_id: str,
        t_min: float | None = None,
        t_max: float | None = None,
        limit: int = 10000,
    ) -> list[Telemetry]:
        stmt = select(Telemetry).where(Telemetry.session_id == session_id)
        if t_min is not None:
            stmt = stmt.where(Telemetry.t >= t_min)
        if t_max is not None:
            stmt = stmt.where(Telemetry.t <= t_max)
        stmt = stmt.order_by(Telemetry.t.asc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def latest(self, session_id: str) -> Optional[Telemetry]:
        stmt = (
            select(Telemetry)
            .where(Telemetry.session_id == session_id)
            .order_by(Telemetry.t.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def recent(
        self, session_id: str, window_sec: float = 10.0
    ) -> list[Telemetry]:
        cutoff = time.time() - window_sec
        return await self.query_by_session(session_id, t_min=cutoff)


# ---------------------------------------------------------------------------
# ConversationRepo
# ---------------------------------------------------------------------------

class ConversationRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(
        self,
        session_id: str,
        agent: str,
        role: str,
        content: str | None = None,
        metadata: dict | None = None,
    ) -> Conversation:
        conv = Conversation(
            session_id=session_id,
            agent=agent,
            role=role,
            content=content,
            metadata_=metadata,
        )
        self.session.add(conv)
        await self.session.commit()
        await self.session.refresh(conv)
        return conv

    async def load_recent(
        self, session_id: str, agent: str, limit: int = 10
    ) -> list[Conversation]:
        stmt = (
            select(Conversation)
            .where(Conversation.session_id == session_id)
            .where(Conversation.agent == agent)
            .order_by(Conversation.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())[::-1]  # chronological order

    async def load_all(self, session_id: str) -> list[Conversation]:
        stmt = (
            select(Conversation)
            .where(Conversation.session_id == session_id)
            .order_by(Conversation.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_session(self, session_id: str) -> int:
        stmt = select(func.count(Conversation.id)).where(
            Conversation.session_id == session_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()


# ---------------------------------------------------------------------------
# Telemetry buffer flush helper
# ---------------------------------------------------------------------------

async def flush_telemetry_buffer(app_state, session_factory) -> None:
    """Periodic task: flush telemetry buffer to DB every second."""
    while True:
        await __import__("asyncio").sleep(1.0)
        if not app_state.telemetry_buffer:
            continue
        if not app_state.session_id:
            app_state.telemetry_buffer.clear()
            continue

        batch = []
        async with app_state.lock:
            batch = list(app_state.telemetry_buffer)
            app_state.telemetry_buffer.clear()

        if not batch:
            continue

        try:
            async with session_factory() as db:
                repo = TelemetryRepo(db)
                await repo.batch_insert(app_state.session_id, batch)
        except Exception as exc:
            logger.error(f"flush_telemetry_buffer: failed: {exc}")


# ---------------------------------------------------------------------------
# run_agent_with_log — wrapper that auto-writes conversations
# ---------------------------------------------------------------------------

async def run_agent_with_log(
    session_id: str,
    agent_name: str,
    message: str,
    session_factory,
    run_fn,
) -> AsyncGenerator[str, None]:
    """Wrap an agent call with auto-logging to conversations table.

    Yields SSE-formatted strings as the agent produces output.
    """
    async with session_factory() as db:
        repo = ConversationRepo(db)
        # Log human message
        await repo.add(session_id, agent_name, "human", content=message)

    try:
        async for chunk in run_fn():
            yield chunk
    except Exception as exc:
        logger.error(f"run_agent_with_log: agent '{agent_name}' error: {exc}")
        async with session_factory() as db:
            repo = ConversationRepo(db)
            await repo.add(
                session_id, "system", "error",
                content=f"Agent '{agent_name}' error: {exc}",
                metadata={"agent": agent_name, "error": str(exc)},
            )
        yield f'data: {{"type":"error","message":"{str(exc)}"}}\n\n'
