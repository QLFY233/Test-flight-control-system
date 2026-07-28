"""
数据仓储 + TelemetryBuffer (每秒批量 flush)。
"""
import time
import asyncio
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert

from db.models import Environment, FlightSession, Telemetry, Conversation
from db.session import async_session

logger = logging.getLogger(__name__)


# ── Environment ──

async def get_environments(session: AsyncSession) -> list[Environment]:
    result = await session.execute(select(Environment).order_by(Environment.created_at.desc()))
    return result.scalars().all()


async def get_environment(session: AsyncSession, env_id: int) -> Environment | None:
    return await session.get(Environment, env_id)


async def save_environment(session: AsyncSession, name: str, data_json: str) -> Environment:
    env = Environment(name=name, data=data_json)
    session.add(env)
    await session.commit()
    return env


# ── FlightSession ──

async def create_session(session: AsyncSession, session_id: str, task_desc: str | None = None) -> FlightSession:
    fs = FlightSession(id=session_id, task_description=task_desc, status="idle")
    session.add(fs)
    await session.commit()
    return fs


async def get_session(session: AsyncSession, session_id: str) -> FlightSession | None:
    return await session.get(FlightSession, session_id)


async def update_session_status(session: AsyncSession, session_id: str, status: str):
    fs = await session.get(FlightSession, session_id)
    if fs:
        fs.status = status
        await session.commit()


async def get_recent_sessions(session: AsyncSession, limit: int = 6) -> list[FlightSession]:
    result = await session.execute(
        select(FlightSession).order_by(FlightSession.created_at.desc()).limit(limit)
    )
    return result.scalars().all()


# ── Telemetry ──

async def get_telemetry_range(
    session: AsyncSession, session_id: str, t_start: float | None = None, t_end: float | None = None
) -> list[Telemetry]:
    stmt = select(Telemetry).where(Telemetry.session_id == session_id)
    if t_start is not None:
        stmt = stmt.where(Telemetry.t >= t_start)
    if t_end is not None:
        stmt = stmt.where(Telemetry.t <= t_end)
    stmt = stmt.order_by(Telemetry.t)
    result = await session.execute(stmt)
    return result.scalars().all()


# ── Conversation ──

async def get_conversations(session: AsyncSession, session_id: str) -> list[Conversation]:
    result = await session.execute(
        select(Conversation).where(Conversation.session_id == session_id).order_by(Conversation.created_at)
    )
    return result.scalars().all()


async def save_conversation(
    session: AsyncSession,
    session_id: str,
    agent: str,
    role: str,
    content: str,
    metadata: dict | None = None,
):
    import json
    conv = Conversation(
        session_id=session_id,
        agent=agent,
        role=role,
        content=content,
        metadata_json=json.dumps(metadata) if metadata else None,
    )
    session.add(conv)
    await session.commit()


# ── TelemetryBuffer helpers ──

def _build_telemetry_rows(batch: list[dict]) -> list[dict]:
    """将遥测记录列表转为 DB insert 行列表。"""
    rows = []
    for item in batch:
        rows.append({
            "session_id": item.get("session_id", ""),
            "t": item.get("t", 0.0),
            "position_x": item["pos"][0] if item.get("pos") else None,
            "position_y": item["pos"][1] if item.get("pos") and len(item["pos"]) > 1 else None,
            "position_z": item["pos"][2] if item.get("pos") and len(item["pos"]) > 2 else None,
            "velocity_x": item["vel"][0] if item.get("vel") and len(item["vel"]) > 0 else None,
            "velocity_y": item["vel"][1] if item.get("vel") and len(item["vel"]) > 1 else None,
            "velocity_z": item["vel"][2] if item.get("vel") and len(item["vel"]) > 2 else None,
            "accel_x": item["accel"][0] if item.get("accel") and len(item["accel"]) > 0 else None,
            "accel_y": item["accel"][1] if item.get("accel") and len(item["accel"]) > 1 else None,
            "accel_z": item["accel"][2] if item.get("accel") and len(item["accel"]) > 2 else None,
            "angular_velocity_x": item["angular_vel"][0] if item.get("angular_vel") and len(item["angular_vel"]) > 0 else None,
            "angular_velocity_y": item["angular_vel"][1] if item.get("angular_vel") and len(item["angular_vel"]) > 1 else None,
            "angular_velocity_z": item["angular_vel"][2] if item.get("angular_vel") and len(item["angular_vel"]) > 2 else None,
            "quat_w": item["quat"][0] if item.get("quat") and len(item["quat"]) > 0 else None,
            "quat_x": item["quat"][1] if item.get("quat") and len(item["quat"]) > 1 else None,
            "quat_y": item["quat"][2] if item.get("quat") and len(item["quat"]) > 2 else None,
            "quat_z": item["quat"][3] if item.get("quat") and len(item["quat"]) > 3 else None,
        })
    return rows


# ── TelemetryBuffer ──

class TelemetryBuffer:
    """缓冲遥测数据, 每秒批量 flush。"""

    def __init__(self, flush_interval: float = 1.0):
        self._buffer: list[dict] = []
        self._flush_interval = flush_interval
        self._running = False
        self._lock = asyncio.Lock()

    async def start(self):
        self._running = True
        asyncio.create_task(self._flush_loop())

    async def stop(self):
        """停止缓冲。先 flush 残留数据再退出。"""
        self._running = False
        # 等待 flush_loop 退出
        await asyncio.sleep(0.05)
        # 最后 flush 一次残留 (flush_loop 退出前已清空 buffer)
        async with self._lock:
            if self._buffer:
                batch = self._buffer[:]
                self._buffer.clear()
                if batch:
                    await self._flush_batch(batch)

    async def append(self, telemetry: dict):
        """追加一条遥测记录。telemetry 含 session_id, t, pos, quat, vel, accel, angular_vel。"""
        async with self._lock:
            self._buffer.append(telemetry)

    async def _flush_loop(self):
        while self._running:
            await asyncio.sleep(self._flush_interval)
            async with self._lock:
                if not self._buffer:
                    continue
                batch = self._buffer[:]
                self._buffer.clear()
            await self._flush_batch(batch)

    async def _flush_batch(self, batch: list[dict]):
        """将一批遥测记录批量写入 DB。"""
        if not batch:
            return
        try:
            rows = _build_telemetry_rows(batch)
            if rows:
                async with async_session() as session:
                    async with session.begin():
                        await session.execute(insert(Telemetry), rows)
            logger.debug(f"[TelemetryBuffer] flushed {len(rows)} rows")
        except Exception as e:
            logger.error(f"[TelemetryBuffer] flush error: {e}")
