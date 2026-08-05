"""
SSE (Server-Sent Events) — β Chat 流式响应。
POST /api/chat/beta → SSE text/tool_call_start/tool_call_result/plan/error 事件。
"""
import json
import logging
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

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

        try:
            # 使用 Pydantic AI Agent.run() 非流式 (先导已验证)
            result = await _beta_agent.run(req.message)

            # 检查是否有待审提议 (β 调用了 propose_to_alpha)
            if _state_ref and _state_ref.pending_proposal:
                proposal = _state_ref.pending_proposal
                yield await _sse_event("plan", {
                    "id": proposal.get("id", ""),
                    "proposalId": proposal.get("id", ""),
                    "title": "飞行计划",
                    "intent": proposal.get("intent", ""),
                    "summary": proposal.get("intent", ""),
                    "status": "pending",
                    # 预翻译动作概要 (propose 时 α 预翻译; 失败兑底 [])
                    "actions": proposal.get("actions", []),
                })

            yield await _sse_event("text", {"content": result.output, "done": True})

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
