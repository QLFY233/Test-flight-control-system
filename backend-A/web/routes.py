"""
REST 路由 — /api/sessions, /api/overview, /api/history/*, /api/environments, /api/proposals, /api/field/config。
"""
import json
import time
import logging
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from bus.protocol import (
    FLIGHT_STATUS_ABORTED, TO_SMALL_MODEL, CALL_TOOL_ABORT, MSG_TYPE_ERROR,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["rest"])

# 全局引用 (由 lifecycle/main 注入)
_state_ref = None
_db_factory = None


# I8: 变更类输入长度上限 (防 LLM 成本放大/滥用)
_MAX_INTENT_LEN = 4096


def set_rest_context(state, db_factory):
    global _state_ref, _db_factory
    _state_ref = state
    _db_factory = db_factory


def _new_session_id() -> str:
    """细粒度会话 id: YYYYMMDDHHMMSS + 纳秒尾 5 位 (与 alpha._log_action 同规则, 防同秒/同毫秒冲突)。"""
    return time.strftime("%Y%m%d%H%M%S") + f"{time.time_ns() % 100_000:05d}"


# ── Pydantic models ──

class ApproveProposalRequest(BaseModel):
    proposal_id: str


class CreateEnvironmentRequest(BaseModel):
    name: str
    data: dict


class CreateSessionRequest(BaseModel):
    task_description: str | None = None
    environment_id: int | None = None


class UpdateSessionRequest(BaseModel):
    status: str | None = None
    task_description: str | None = None


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

    # I2: 原子认领 — 锁内取出并立即清空, 杜绝并发 approve 重复注入 α 队列
    async with s._lock:
        pending = s.pending_proposal
        if not pending or pending.get("id") != proposal_id:
            raise HTTPException(404, f"proposal {proposal_id} not found or already processed")
        s.pending_proposal = None

    intent = pending.get("intent", "")
    if intent:
        if len(intent) > _MAX_INTENT_LEN:  # I8: 输入长度上限
            raise HTTPException(400, f"intent too long (> {_MAX_INTENT_LEN})")
        await s.push_alpha_input(intent)
        logger.info(f"[routes] proposal {proposal_id} approved → α queue")

    pending["status"] = "approved"

    return {"status": "approved", "proposal_id": proposal_id}


@router.post("/proposals/{proposal_id}/reject")
async def reject_proposal(proposal_id: str):
    """驳回 β 的飞行提议。"""
    s = _state_ref
    if not s:
        raise HTTPException(503, "state not available")

    # I2: 原子认领 (与 approve 对称)
    async with s._lock:
        pending = s.pending_proposal
        if not pending or pending.get("id") != proposal_id:
            raise HTTPException(404, f"proposal {proposal_id} not found")
        s.pending_proposal = None

    pending["status"] = "rejected"

    return {"status": "rejected", "proposal_id": proposal_id}


# ── 会话 ──

@router.get("/sessions")
async def list_sessions(limit: int = Query(10, le=100)):  # N5: limit 上限 100, 防 ?limit=100000 拖垮 DB
    try:
        async with _db_factory() as session:
            from db.repos import list_sessions_with_stats
            rows = await list_sessions_with_stats(session, limit=limit)
            return {"sessions": rows}
    except Exception as e:
        logger.exception(f"Failed: {e}")
        raise HTTPException(500, "Internal server error")


@router.post("/sessions")
async def create_session_endpoint(req: CreateSessionRequest):
    """创建新试飞会话 (前端 spec: POST /api/sessions)。"""
    try:
        async with _db_factory() as session:
            from db.repos import create_session as _create_session
            session_id = _new_session_id()
            fs = await _create_session(session, session_id, req.task_description)
            if req.environment_id is not None:
                fs.environment_id = req.environment_id
                await session.commit()
            if _state_ref:
                _state_ref.session_id = session_id
                # 新建任务: 旧任务的待审提议/自动命名不串入新任务 (防跨任务批准)
                _state_ref.pending_proposal = None
                _state_ref.pending_task_name = None
            return {
                "id": fs.id,
                "status": fs.status,
                "created_at": str(fs.created_at) if fs.created_at else None,
            }
    except Exception as e:
        logger.exception(f"Failed: {e}")
        raise HTTPException(500, "Internal server error")


@router.get("/sessions/{session_id}")
async def get_session_detail_endpoint(session_id: str):
    """会话详情 (#11 刷新恢复: 任务描述/beta_plan/alpha_actions/环境名/遥测条数)。"""
    try:
        async with _db_factory() as session:
            from db.repos import get_session_detail
            detail = await get_session_detail(session, session_id)
            if detail is None:
                raise HTTPException(404, f"session {session_id} not found")
            return detail
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed: {e}")
        raise HTTPException(500, "Internal server error")


@router.patch("/sessions/{session_id}")
async def update_session_endpoint(session_id: str, req: UpdateSessionRequest):
    """更新会话状态/描述 (前端 spec: PATCH /api/sessions/{id})。"""
    try:
        async with _db_factory() as session:
            from db.repos import get_session as _get_session
            fs = await _get_session(session, session_id)
            if fs is None:
                raise HTTPException(404, f"session {session_id} not found")
            if req.status is not None:
                fs.status = req.status
            if req.task_description is not None:
                fs.task_description = req.task_description
            await session.commit()
            return {"id": fs.id, "status": fs.status}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed: {e}")
        raise HTTPException(500, "Internal server error")


@router.post("/sessions/{session_id}/activate")
async def activate_session_endpoint(session_id: str):
    """恢复任务: 切换当前会话到指定任务 (前端任务管理面板)。

    仅切 AppState.session_id (后续 β 对话/α 动作/遥测写入该任务);
    旧任务的在内存待审提议清空, 防跨任务批准串扰。
    """
    try:
        async with _db_factory() as session:
            from db.repos import get_session as _get_session
            fs = await _get_session(session, session_id)
            if fs is None:
                raise HTTPException(404, f"session {session_id} not found")
            status = fs.status
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed: {e}")
        raise HTTPException(500, "Internal server error")

    s = _state_ref
    if s:
        s.session_id = session_id
        s.pending_proposal = None
        logger.info(f"[routes] task activated: {session_id}")
    return {"id": session_id, "status": status}


@router.delete("/sessions/{session_id}")
async def delete_session_endpoint(session_id: str):
    """删除任务记录: 级联删除对话 + 遥测 + 会话行。

    若删除的是当前任务, 清空 AppState.session_id + 待审提议
    (前端随即新建任务承接; 期间遥测缓冲不落库, 毫秒级窗口可接受)。
    """
    try:
        async with _db_factory() as session:
            from db.repos import delete_session as _delete_session
            deleted = await _delete_session(session, session_id)
            if not deleted:
                raise HTTPException(404, f"session {session_id} not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed: {e}")
        raise HTTPException(500, "Internal server error")

    s = _state_ref
    was_active = False
    if s and s.session_id == session_id:
        s.session_id = None
        s.pending_proposal = None
        s.pending_task_name = None
        was_active = True
    logger.info(f"[routes] task deleted: {session_id} (was_active={was_active})")
    return {"status": "deleted", "session_id": session_id, "was_active": was_active}


@router.post("/sessions/{session_id}/abort")
async def abort_session_endpoint(session_id: str):
    """中止会话 (前端 spec 行 562) — 本地状态置 aborted + 经 IPC 下发 call.abort。"""
    s = _state_ref
    if s:
        s.flight_status = FLIGHT_STATUS_ABORTED
        s.current_action_plan = None

    try:
        from bus.router import call as bus_call
        result = await bus_call(
            to=TO_SMALL_MODEL, tool=CALL_TOOL_ABORT, args={}, _from="routes"
        )
        if result.get("msg_type") == MSG_TYPE_ERROR:
            detail = result.get("payload", {}).get("error", "unknown")
            logger.error(f"[routes] abort dispatch failed: {detail}")
            raise HTTPException(502, f"abort dispatch failed: {detail}")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[routes] abort dispatch error: {e}")
        raise HTTPException(502, "abort dispatch error")

    try:
        async with _db_factory() as session:
            from db.repos import update_session_status
            await update_session_status(session, session_id, FLIGHT_STATUS_ABORTED)
    except Exception:
        pass  # 会话行可能不存在 — 本地状态已更新, 不阻断

    return {"status": "aborted", "session_id": session_id}

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
async def get_telemetry(
    session_id: str,
    t_from: float = 0,          # 契约 🟢: 参数名对齐 spec (原 t_start)
    t_end: float | None = None,
    limit: int = Query(1000, le=10000),  # N4: 显式 limit, 静默截断改为受控分页
):
    try:
        async with _db_factory() as session:
            from db.repos import get_telemetry_range
            rows = await get_telemetry_range(session, session_id, t_from, t_end)
            # 2026-08-06: 补全 accel/angular_vel/quat — 历史页回放需看板全量数据;
            # 兼容历史行 NULL 列 → 0.0, 保证数组字段恒为定长数值
            def _v(*vals):
                return [0.0 if v is None else float(v) for v in vals]
            data = [
                {
                    "t": r.t,
                    "pos": _v(r.position_x, r.position_y, r.position_z),
                    "vel": _v(r.velocity_x, r.velocity_y, r.velocity_z),
                    "accel": _v(r.accel_x, r.accel_y, r.accel_z),
                    "angular_vel": _v(r.angular_velocity_x, r.angular_velocity_y, r.angular_velocity_z),
                    "quat": _v(r.quat_w, r.quat_x, r.quat_y, r.quat_z),
                }
                for r in rows[:limit]
            ]
            return {"session_id": session_id, "count": len(data), "data": data}
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
