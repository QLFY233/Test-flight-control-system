"""
SSE (Server-Sent Events) — β Chat 流式响应。
POST /api/chat/beta → SSE text/tool_call_start/tool_call_result/plan/error 事件。

2026-08-05 (#7): 改流式输出 — agent.run() → agent.run_stream(), text 事件逐 chunk 下发。
2026-08-05 (修复): run_stream 默认不执行工具调用 → 改 run_stream_events() (工具自动执行 + 增量文本流)。
"""
import json
import logging
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from pydantic_ai import (
    PartDeltaEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    TextPartDelta,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])

# 全局 β agent 引用 (由 lifecycle 注入)
_beta_agent = None


def set_beta_agent(agent):
    """注入 β agent 实例。"""
    global _beta_agent
    _beta_agent = agent


class ChatRequest(BaseModel):
    message: str = Field(..., max_length=4096)  # I8: 输入长度上限 (防 LLM 成本放大)
    session_id: str | None = None


async def _sse_event(event_type: str, data: dict) -> str:
    """生成一条 SSE 事件。"""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event_type}\ndata: {payload}\n\n"


async def _ensure_session() -> str | None:
    """确保存在当前会话: AppState.session_id 为空则新建 (对齐 alpha._log_action 规则, #11 对话续接)。"""
    from tools.beta_tools import _state_ref
    if not _state_ref:
        return None
    if not _state_ref.session_id:
        import time as _time
        _state_ref.session_id = (
            _time.strftime("%Y%m%d%H%M%S") + f"{_time.time_ns() % 100_000:05d}"
        )
        try:
            from db.repos import get_session as _get, create_session as _create
            from db.session import async_session as _db_sess
            async with _db_sess() as db:
                existing = await _get(db, _state_ref.session_id)
                if existing is None:
                    await _create(db, _state_ref.session_id, task_desc=None)
        except Exception as e:
            logger.warning(f"[sse] ensure_session create failed: {e}")
    return _state_ref.session_id


async def _save_conv(session_id: str, agent: str, role: str, content: str):
    """写入一条对话记录 (#11 对话持久化, 刷新后可恢复)。"""
    try:
        from db.repos import save_conversation
        from db.session import async_session as _db_sess
        async with _db_sess() as db:
            await save_conversation(db, session_id, agent, role, content)
    except Exception as e:
        logger.warning(f"[sse] save conversation failed: {e}")


@router.post("/beta")
async def chat_beta(req: ChatRequest):
    """β Chat SSE 端点 — 接收人类消息, 返回 β 流式回复。

    SSE 事件类型:
    - text: β 流式文字片段
    - tool_call_start: β 调用工具开始
    - tool_call_result: 工具返回结果
    - plan: β 飞行计划 (动作意图概要 + proposalId)
    - error: 错误
    """

    async def event_stream():
        if _beta_agent is None:
            yield await _sse_event("error", {"message": "β agent not initialized"})
            return

        # 保存人最后的消息 (供 forward_last_human_message 使用)
        from tools.beta_tools import _state_ref
        if _state_ref:
            _state_ref.last_human_message_to_beta = req.message

        # #11 对话持久化: 确保会话存在 + 存人类消息 (刷新后恢复 β 对话)
        session_id = await _ensure_session()
        if session_id:
            await _save_conv(session_id, "beta", "human", req.message)

        try:
            # 流式: run_stream_events() 逐事件流 (2026-08-05 修复 — run_stream 在
            # 默认 end_strategy 下**不执行工具调用** (pydantic-ai 2.0 文档: "tool calls
            # will not run in streaming mode with the default settings"), 导致 β 文本后
            # 调 get_field_map 等工具时 agent 卡死无输出。run_stream_events() 才会
            # 在工具调用期间持续运行并流出全部事件。
            # TextPartDelta.content_delta 为**增量**文本 (非累积), 直接发前端追加。
            full_text = ""
            async with _beta_agent.run_stream_events(req.message) as result:
                async for event in result:
                    if isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
                        delta = event.delta.content_delta
                        if delta:
                            full_text += delta
                            yield await _sse_event("text", {"content": delta})
                    elif isinstance(event, FunctionToolCallEvent):
                        yield await _sse_event("tool_call_start", {
                            "name": event.part.tool_name,
                            "args": event.part.args if isinstance(event.part.args, str) else str(event.part.args or ""),
                        })
                    elif isinstance(event, FunctionToolResultEvent):
                        content = event.part.content
                        yield await _sse_event("tool_call_result", {
                            "name": event.part.tool_name or "",
                            "result": content if isinstance(content, str) else str(content or ""),
                        })
                    # AgentRunResultEvent: 最终结果确认, 文本已由 delta 事件发完, 无需处理

            # #11: 流结束后存 β 完整回复
            if session_id and full_text:
                await _save_conv(session_id, "beta", "agent", full_text)

            # 流结束后检查是否有待审提议 (β 调用了 propose_to_alpha)
            if _state_ref and _state_ref.pending_proposal:
                proposal = _state_ref.pending_proposal
                yield await _sse_event("plan", {
                    "id": proposal.get("id", ""),
                    "proposalId": proposal.get("id", ""),
                    "title": proposal.get("title") or proposal.get("task_name") or "飞行计划",
                    "task_name": proposal.get("task_name") or "",
                    "intent": proposal.get("intent", ""),
                    "summary": proposal.get("intent", ""),
                    "status": "pending",
                    # 预翻译动作概要 (propose 时 α 预翻译; 失败兑底 [])
                    "actions": proposal.get("actions", []),
                })

        except Exception as e:
            logger.exception(f"[sse] β stream error: {e}")
            yield await _sse_event("error", {"message": "Internal server error"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
