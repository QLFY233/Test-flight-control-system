"""
REST 路由 — /api/sessions, /api/overview, /api/history/*, /api/environments, /api/proposals, /api/field/config。
"""
import json
import time
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["rest"])

# 全局引用 (由 lifecycle/main 注入)
_state_ref = None
_db_factory = None


def set_rest_context(state, db_factory):
    global _state_ref, _db_factory
    _state_ref = state
    _db_factory = db_factory


# ── Pydantic models ──

class ApproveProposalRequest(BaseModel):
    proposal_id: str


class CreateEnvironmentRequest(BaseModel):
    name: str
    data: dict


# ── 健康检查 ──

@router.get("/health")
async def health():
    return {"status": "ok", "backend": "A"}


# ── 场地配置 ──

@router.get("/field/config")
async def get_field_config():
    s = _state_ref
    if not s:
        raise HTTPException(503, "state not available")
    return s.config.field_cfg


# ── 当前位姿 ──

@router.get("/current-pose")
async def get_current_pose():
    s = _state_ref
    if not s:
        raise HTTPException(503, "state not available")
    p = s.current_pose
    return {
        "pos": p.pos,
        "quat": p.quat,
        "vel": p.vel,
        "ts": p.ts,
    }


# ── 提议审核 (C3 单一路径) ──

@router.get("/proposals")
async def list_proposals():
    s = _state_ref
    if not s:
        raise HTTPException(503, "state not available")
    pending = s.pending_proposal
    return {"proposals": [pending] if pending else []}


@router.post("/proposals/{proposal_id}/approve")
async def approve_proposal(proposal_id: str):
    """批准 β 的飞行提议 → 注入 α 输入队列。
    C3 单一路径 — 废弃 /api/plan/approve。
    """
    s = _state_ref
    if not s:
        raise HTTPException(503, "state not available")

    pending = s.pending_proposal
    if not pending or pending.get("id") != proposal_id:
        raise HTTPException(404, f"proposal {proposal_id} not found or already processed")

    intent = pending.get("intent", "")
    if intent:
        await s.push_alpha_input(intent)
        logger.info(f"[routes] proposal {proposal_id} approved → α queue")

    # 标记为已处理
    pending["status"] = "approved"
    s.pending_proposal = None

    return {"status": "approved", "proposal_id": proposal_id}


@router.post("/proposals/{proposal_id}/reject")
async def reject_proposal(proposal_id: str):
    """驳回 β 的飞行提议。"""
    s = _state_ref
    if not s:
        raise HTTPException(503, "state not available")

    pending = s.pending_proposal
    if not pending or pending.get("id") != proposal_id:
        raise HTTPException(404, f"proposal {proposal_id} not found")

    pending["status"] = "rejected"
    s.pending_proposal = None

    return {"status": "rejected", "proposal_id": proposal_id}


# ── 会话 ──

@router.get("/sessions")
async def list_sessions(limit: int = 10):
    try:
        async with _db_factory() as session:
            from db.repos import get_recent_sessions
            rows = await get_recent_sessions(session, limit=limit)
            return {
                "sessions": [
                    {
                        "id": r.id,
                        "created_at": str(r.created_at) if r.created_at else None,
                        "task_description": r.task_description,
                        "status": r.status,
                    }
                    for r in rows
                ]
            }
    except Exception as e:
        logger.exception(f"Failed: {e}")
        raise HTTPException(500, "Internal server error")

@router.get("/overview")
async def get_overview():
    """系统总览 — 最近会话 + 当前状态。"""
    s = _state_ref
    overview = {
        "flight_status": s.flight_status if s else "unknown",
        "ipc_connected": s.ipc_connected if s else False,
        "session_id": s.session_id if s else None,
        "last_llm_ok": s.last_llm_call_ok if s else True,
    }
    try:
        async with _db_factory() as session:
            from db.repos import get_recent_sessions
            recent = await get_recent_sessions(session, limit=6)
            overview["recent_sessions"] = [
                {"id": r.id, "status": r.status, "task": r.task_description}
                for r in recent
            ]
    except Exception:
        overview["recent_sessions"] = []
    return overview


# ── 历史 ──

@router.get("/history/telemetry/{session_id}")
async def get_telemetry(session_id: str, t_start: float = 0, t_end: float | None = None):
    try:
        async with _db_factory() as session:
            from db.repos import get_telemetry_range
            rows = await get_telemetry_range(session, session_id, t_start, t_end)
            return {
                "session_id": session_id,
                "count": len(rows),
                "data": [
                    {
                        "t": r.t,
                        "pos": [r.position_x, r.position_y, r.position_z],
                        "vel": [r.velocity_x, r.velocity_y, r.velocity_z],
                    }
                    for r in rows[:1000]
                ],
            }
    except Exception as e:
        logger.exception(f"Failed: {e}")
        raise HTTPException(500, "Internal server error")

@router.get("/history/conversations/{session_id}")
async def get_conversations(session_id: str):
    try:
        async with _db_factory() as session:
            from db.repos import get_conversations
            rows = await get_conversations(session, session_id)
            return {
                "session_id": session_id,
                "count": len(rows),
                "data": [
                    {"agent": r.agent, "role": r.role, "content": r.content, "created_at": str(r.created_at)}
                    for r in rows
                ],
            }
    except Exception as e:
        logger.exception(f"Failed: {e}")
        raise HTTPException(500, "Internal server error")

# ── 环境 ──

@router.get("/environments")
async def list_environments():
    try:
        async with _db_factory() as session:
            from db.repos import get_environments
            rows = await get_environments(session)
            return {"environments": [{"id": r.id, "name": r.name, "data": r.data} for r in rows]}
    except Exception as e:
        logger.exception(f"Failed: {e}")
        raise HTTPException(500, "Internal server error")

@router.post("/environments")
async def create_environment(req: CreateEnvironmentRequest):
    try:
        async with _db_factory() as session:
            from db.repos import save_environment
            env = await save_environment(session, req.name, json.dumps(req.data))
            s = _state_ref
            if s:
                s.current_environment = req.data
                s.environment_id = env.id
            return {"id": env.id, "name": env.name}
    except Exception as e:
        logger.exception(f"Failed: {e}")
        raise HTTPException(500, "Internal server error")

# ── 链路状态 ──

@router.get("/link-status")
async def link_status():
    s = _state_ref
    if not s:
        raise HTTPException(503, "state not available")
    return {
        "ipc": "up" if s.ipc_connected else "down",
        "llm": "ok" if s.last_llm_call_ok else "error",
        "flight_status": s.flight_status,
    }
