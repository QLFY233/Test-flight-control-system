"""
SSE (Server-Sent Events) — β Chat 流式响应。
POST /api/chat/beta → SSE text/tool_call_start/tool_call_result/plan/error 事件。

2026-08-05 (#7): 改流式输出 — agent.run() → agent.run_stream(), text 事件逐 chunk 下发。
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
            # 流式: run_stream → stream_text() 逐 token 产出 text 事件 (2026-08-05 #7)。
            # 注: pydantic-ai 2.0 stream_text() 产出**累积文本** (每 chunk = 到当前为止的全部),
            # 需与上一 chunk 求差得到增量, 否则前端逐 chunk 追加会重复。
            # 工具调用 (propose_to_alpha 等) 在流内自动执行, 结果经 _state_ref 读取。
            async with _beta_agent.run_stream(req.message) as result:
                prev = ""
                async for chunk in result.stream_text():
                    delta = chunk[len(prev):] if chunk.startswith(prev) else chunk
                    prev = chunk
                    if delta:
                        yield await _sse_event("text", {"content": delta})

            # 流结束后检查是否有待审提议 (β 调用了 propose_to_alpha)
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
