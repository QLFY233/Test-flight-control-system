"""
β 工具集 — β Agent (中枢大模型) 可通过工具调用的函数。
所有工具经消息总线调度各组件 (龙虾模式)。
"""
import json
import time
import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

# 全局引用 (由 lifecycle 注入)
_state_ref = None  # AppState
_bus_ref = None    # bus.router.call
_db_ref = None     # db.repos + session
_dashboard_broadcast_ref = None  # web.ws.broadcast_dashboard_config (β 工具驱动看板)

# 预翻译用 α 翻译器 (lazy 单例; 复用生命周期内, 不随每次提议重建)
_pre_translator_ref = None


def _get_pre_translator():
    """懒创建预翻译用 α 翻译器 (对齐 lifecycle 的 make_translator 工厂)。
    预翻译与正式翻译共用同一 LLM 链路, 但实例独立 (不影响 α loop)。
    """
    global _pre_translator_ref
    if _pre_translator_ref is None:
        from agents.alpha import make_translator
        _pre_translator_ref = make_translator()
    return _pre_translator_ref


async def _pre_translate(intent: str, state) -> list:
    """预翻译 intent → ActionCommand.actions (供前端渲染待批准航线预览)。
    失败/超时/无 key → 兜底 [] (不影响 propose 主流程)。
    """
    try:
        translator = _get_pre_translator()
        pose = {
            "pos": state.current_pose.pos,
            "quat": state.current_pose.quat,
            "vel": state.current_pose.vel,
        }
        env = {}  # 先导为空 (对齐 alpha loop)
        # LLM 调用耗时 1~5s, to_thread 避免阻塞事件循环; translate 内部线程安全
        action_cmd = await asyncio.to_thread(translator.translate, intent, pose, env)
        actions = action_cmd.get("actions", []) if isinstance(action_cmd, dict) else []
        if not isinstance(actions, list):
            actions = []
        logger.info(f"[beta-tools] pre-translate OK: {len(actions)} actions")
        return actions
    except Exception as e:
        logger.warning(f"[beta-tools] pre-translate failed (fallback []): {e}")
        return []


# 动作编码 → 中文标签 (任务名摘要用, #3)
_ACTION_LABELS = {
    "takeoff": "起飞", "land": "降落", "goto": "飞往", "move": "移动",
    "climb": "爬升", "descend": "下降", "yaw": "转向", "hover": "悬停",
    "return_home": "返航",
}


def _derive_task_name(intent: str, actions: list) -> str:
    """从预翻译动作序列生成简洁任务名 (AI 翻译产物的结构化摘要)。
    有动作 → "起飞1m→飞往(3,2)→悬停2s…"; 无动作 → 截断意图; 空 → 兜底。
    """
    if actions:
        parts = []
        for a in actions[:4]:
            code = a.get("code", "")
            label = _ACTION_LABELS.get(code, code.upper())
            val = a.get("value")
            tgt = a.get("target")
            units = a.get("units", "")
            if code == "goto" and isinstance(tgt, (list, tuple)) and len(tgt) >= 2 and all(isinstance(v, (int, float)) for v in tgt[:2]):
                parts.append(f"飞往({tgt[0]:g},{tgt[1]:g})")
            elif isinstance(val, (int, float)):
                parts.append(f"{label}{val:g}{units}")
            else:
                parts.append(label)
        name = "→".join(parts)
        if len(actions) > 4:
            name += "…"
        if name:
            return name[:30]
    cleaned = " ".join((intent or "").split())
    if cleaned:
        return cleaned[:24] + ("…" if len(cleaned) > 24 else "")
    return "试飞任务"


def set_tool_context(state, bus, db_session_factory):
    """注入工具依赖 (由 lifecycle 在启动时调用)。"""
    global _state_ref, _bus_ref, _db_ref
    _state_ref = state
    _bus_ref = bus
    _db_ref = db_session_factory


def set_dashboard_broadcast(fn):
    """注入看板配置广播回调 (由 lifecycle 在启动时调用)。"""
    global _dashboard_broadcast_ref
    _dashboard_broadcast_ref = fn


def _log_push_error(task):
    """记录 push_alpha_input 异步任务中的异常。"""
    exc = task.exception()
    if exc:
        logger.error(f"[beta-tools] push_alpha_input failed: {exc}")


# ── 实时状态查询 ──


def get_field_map() -> dict:
    """返回场地边界 + home (先导仅 home/boundary, 无 obstacles)。"""
    s = _state_ref
    if not s:
        return {"error": "state not available"}
    field = s.config.field_cfg
    return {
        "boundary": field.get("boundary", {}),
        "home": field.get("home", {}),
    }


def get_current_pose() -> dict:
    """返回无人机当前位姿/速度 (从 B 上行缓存)。"""
    s = _state_ref
    if not s:
        return {"error": "state not available"}
    p = s.current_pose
    return {
        "pos": p.pos,
        "quat": p.quat,
        "vel": p.vel,
        "accel": p.accel,
        "angular_vel": p.angular_vel,
        "ts": p.ts,
    }


def get_recent_telemetry(window_sec: float = 10.0) -> dict:
    """返回最近 window_sec 秒的遥测 (从 AppState 缓存)。"""
    s = _state_ref
    if not s:
        return {"error": "state not available"}
    # 先导: 返回最新位姿 + 时间戳
    p = s.current_pose
    return {
        "latest": {
            "pos": p.pos,
            "vel": p.vel,
            "ts": p.ts,
        },
        "window_sec": window_sec,
        "note": "full telemetry history available via query_telemetry",
    }


def get_current_environment() -> dict:
    """返回当前环境条件 (environments.data JSON)。"""
    s = _state_ref
    if not s:
        return {"error": "state not available"}
    if s.current_environment:
        return {"environment": s.current_environment}
    return {"environment": None, "note": "no environment set for this session"}


# ── 历史查询 ──


async def query_sessions(limit: int = 10) -> dict:
    """返回最近试飞会话列表。"""
    try:
        async with _db_ref() as session:
            from db.repos import get_recent_sessions as _recent
            sessions = await _recent(session, limit=limit)
            return {
                "sessions": [
                    {
                        "id": s.id,
                        "created_at": str(s.created_at) if s.created_at else None,
                        "task_description": s.task_description,
                        "status": s.status,
                    }
                    for s in sessions
                ]
            }
    except Exception as e:
        logger.error(f"[beta-tools] query_sessions error: {e}")
        return {"error": str(e)}


async def query_telemetry(session_id: str, t_start: float = 0, t_end: float | None = None) -> dict:
    """返回指定会话的轨迹数据。"""
    try:
        async with _db_ref() as session:
            from db.repos import get_telemetry_range as _range
            rows = await _range(session, session_id, t_start, t_end)
            return {
                "session_id": session_id,
                "count": len(rows),
                "telemetry": [
                    {
                        "t": r.t,
                        "pos": [r.position_x, r.position_y, r.position_z],
                        "vel": [r.velocity_x, r.velocity_y, r.velocity_z],
                    }
                    for r in rows[:500]  # 限制返回量
                ],
            }
    except Exception as e:
        logger.error(f"[beta-tools] query_telemetry error: {e}")
        return {"error": str(e)}


async def query_environment(env_id: int) -> dict:
    """返回指定环境条件。"""
    try:
        async with _db_ref() as session:
            from db.repos import get_environment
            env = await get_environment(session, env_id)
            if env:
                return {"id": env.id, "name": env.name, "data": env.data}
            return {"error": f"environment {env_id} not found"}
    except Exception as e:
        logger.error(f"[beta-tools] query_environment error: {e}")
        return {"error": str(e)}


async def query_conversations(session_id: str) -> dict:
    """返回指定会话的对话记录。"""
    try:
        async with _db_ref() as session:
            from db.repos import get_conversations as _conv
            rows = await _conv(session, session_id)
            return {
                "session_id": session_id,
                "count": len(rows),
                "conversations": [
                    {
                        "agent": r.agent,
                        "role": r.role,
                        "content": r.content[:200] if r.content else "",
                        "created_at": str(r.created_at),
                    }
                    for r in rows
                ],
            }
    except Exception as e:
        logger.error(f"[beta-tools] query_conversations error: {e}")
        return {"error": str(e)}


# ── α 调度 (2 条安全路径) ──

# ⚠️ 安全边界关键:
#   propose_to_alpha — 总线层拦截 → 存 pending_proposal → 人审核 → 才进 α 队列
#   forward_last_human_message — 免审直接进 α 队列 (人已发话)


async def propose_to_alpha(intent: str) -> dict:
    """β 的自主飞行提议 — 必须人审核后才注入 α。
    总线层拦截: 存储到 pending_proposal，前端展示待审卡片。
    人点击[批准]后由 /api/proposals/*/approve 注入 α 队列。
    预翻译 intent → actions (LLM, 1~5s) 供前端渲染待批准航线预览; 失败兑底 []。
    """
    s = _state_ref
    if not s:
        return {"error": "state not available"}

    proposal = {
        "id": f"proposal-{time.time_ns()}",
        "intent": intent,
        "from": "beta",
        "status": "pending",
        "created_at": time.time(),
        "actions": [],
    }
    # 预翻译: intent → ActionCommand.actions (LLM 1~5s; 失败兑底 [] 不影响提议)
    proposal["actions"] = await _pre_translate(intent, s)
    # #3: 自动生成任务名 (动作摘要; 无动作截断意图) — 供 FlightPlanCard 标题 + 会话 task_description
    task_name = _derive_task_name(intent, proposal["actions"])
    proposal["task_name"] = task_name
    proposal["title"] = task_name
    s.pending_task_name = task_name
    s.pending_proposal = proposal

    logger.info(f"[beta-tools] propose_to_alpha: {intent[:80]}... (pending approval, {len(proposal['actions'])} pre-translated actions)")
    return {
        "status": "pending_approval",
        "proposal_id": proposal["id"],
        "message": "飞行提议已生成，请在前端确认后执行。",
    }


def forward_last_human_message() -> dict:
    """转发人对 β 说的最后一条消息直接进 α 队列。
    免审核 — 人已发话。
    metadata: path='forward', approved=True。
    """
    s = _state_ref
    if not s:
        return {"error": "state not available"}

    msg = s.last_human_message_to_beta
    if not msg:
        return {"status": "no_message", "message": "没有待转发的人话指令。"}

    # 直接注入 α 输入队列 (可能在 async 或 sync 上下文)
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        task = asyncio.ensure_future(s.push_alpha_input(msg))
        task.add_done_callback(_log_push_error)
    except RuntimeError:
        # 无运行中的事件循环 — 创建临时 loop 执行
        asyncio.run(s.push_alpha_input(msg))

    logger.info(f"[beta-tools] forward_last_human_message (免审): {msg[:80]}...")
    return {
        "status": "forwarded",
        "message": "指令已直接发给 α 执行。",
    }


# ── analytics 工具 (阶段 L 实现) ──

_fft_analyzer = None
_stats_analyzer = None
_filter_tool = None


def _get_fft():
    global _fft_analyzer
    if _fft_analyzer is None:
        from analytics.fft import FFTAnalyzer
        _fft_analyzer = FFTAnalyzer()
    return _fft_analyzer


def _get_stats():
    global _stats_analyzer
    if _stats_analyzer is None:
        from analytics.stats import StatsAnalyzer
        _stats_analyzer = StatsAnalyzer()
    return _stats_analyzer


def _get_filter():
    global _filter_tool
    if _filter_tool is None:
        from analytics.filter import FilterTool
        _filter_tool = FilterTool()
    return _filter_tool


def analytics_fft(data: list, options: dict | None = None) -> dict:
    """FFT 频谱分析。"""
    return _get_fft().run(data, options)


def analytics_stats(data: list, metric: str = "all") -> dict:
    """统计分析 — mean/variance/std/minmax/trend。"""
    return _get_stats().run(data, metric)


def analytics_filter(data: list, filter_type: str = "moving_average", params: dict | None = None) -> dict:
    """数字滤波 — moving_average/lowpass/highpass。"""
    return _get_filter().run(data, filter_type, params)


# ── 看板驱动 (阶段 L, 先导 stub → 2026-08-06 接通真广播) ──


async def _push_dashboard_config(panel_id: str, spec: dict | None, filter_spec: dict | None):
    """经 WS dashboard_config 推送前端 (未注入广播回调时静默跳过 — 看板配置不影响主流程)。"""
    fn = _dashboard_broadcast_ref
    if not fn:
        return
    try:
        await fn(panel_id, spec, filter_spec)
    except Exception as e:
        logger.warning(f"[beta-tools] dashboard_config broadcast failed: {e}")


async def dashboard_configure(panel_id: str, spec: dict) -> dict:
    """配置看板面板 (推送 WS dashboard_config, 前端实时切换展示内容)。"""
    await _push_dashboard_config(panel_id, spec, None)
    return {
        "status": "ok",
        "panel_id": panel_id,
        "spec": spec,
    }


async def dashboard_set_filter(panel_id: str, filter_spec: dict) -> dict:
    """设置看板筛选器 (推送 WS dashboard_config, 前端 FilterBar 应用)。"""
    await _push_dashboard_config(panel_id, None, filter_spec)
    return {
        "status": "ok",
        "panel_id": panel_id,
        "filter": filter_spec,
    }


def dashboard_list_panels() -> dict:
    """列出可用看板面板。"""
    return {
        "panels": [
            {"id": "altitude", "name": "高度图", "type": "line_chart", "source": "pose.z"},
            {"id": "velocity", "name": "速度图", "type": "line_chart", "source": "pose.vel"},
            {"id": "field_map", "name": "场地俯视图", "type": "scatter", "source": "pose.xy"},
            {"id": "fft_spectrum", "name": "频谱分析", "type": "bar_chart", "source": "analytics.fft"},
            {"id": "stats_summary", "name": "统计摘要", "type": "stat_tiles", "source": "analytics.stats"},
        ],
    }
