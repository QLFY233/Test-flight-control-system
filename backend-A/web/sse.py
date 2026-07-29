"""
SSE (Server-Sent Events) — β Chat 流式响应。
POST /api/chat/beta → SSE text/tool_call_start/tool_call_result/plan/error 事件。
"""
import json
import time
import logging
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])

# 全局 β agent 引用 (由 lifecycle 注入)
_beta_agent = None


def set_beta_agent(agent):
    """注入 β agent 实例。"""
    global _beta_agent
    _beta_agent = agent


class ChatRequest(BaseModel):
    message: str
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
            # 使用 Pydantic AI Agent.run() 流式
            async with _beta_agent.run_stream(req.message) as stream:
                async for chunk in stream:
                    chunk_type = chunk.__class__.__name__ if hasattr(chunk, '__class__') else type(chunk).__name__

                    # 文本片段
                    if hasattr(chunk, 'text'):
                        delta = chunk.text
                        if delta:
                            yield await _sse_event("text", {"content": delta})
                    elif hasattr(chunk, 'content'):
                        delta = chunk.content
                        if isinstance(delta, str) and delta:
                            yield await _sse_event("text", {"content": delta})

                    # 工具调用开始
                    if hasattr(chunk, 'tool_name') and chunk.tool_name:
                        yield await _sse_event("tool_call_start", {
                            "tool_name": chunk.tool_name,
                            "args": getattr(chunk, 'tool_args', {}),
                        })

                    # 工具调用结果
                    if hasattr(chunk, 'tool_result'):
                        yield await _sse_event("tool_call_result", {
                            "tool_name": getattr(chunk, 'tool_name', ''),
                            "result": chunk.tool_result,
                        })

            # 发送最终消息 (非流式备选)
            yield await _sse_event("text", {"content": "", "done": True})

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
