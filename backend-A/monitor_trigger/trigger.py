"""
异常监控触发器 — 接收 B→A alert event, 转发前端 (WS) + 唤醒 β 给处置建议。
alert 由 bridge._handle_alert 已做 WS broadcast, 本模块负责 β 唤醒逻辑 (阶段 H 已具备)。
"""
import logging

logger = logging.getLogger(__name__)

# 全局引用 (由 lifecycle 注入)
_state_ref = None


def set_state(state):
    global _state_ref
    _state_ref = state


async def handle_alert(alert: dict):
    """处理 B→A alert — 唤醒 β 给处置建议 (阶段 I 实现)。

    alert 已由 bridge._handle_alert 做 WS broadcast。
    本函数负责将告警信息注入 β 上下文, 使其在下一轮对话中可被 β 感知。
    """
    code = alert.get("code", "unknown")
    detail = alert.get("detail", "")
    level = alert.get("level", "warning")

    logger.info(f"[monitor-trigger] alert received: [{level}] {code} — {detail}")

    # 唤醒 β: 将 alert 推入 system messages (供前端 β 聊天流展示)
    # 阶段 I 先导: alert 已经通过 WS broadcast 到前端,
    # 前端将其作为系统消息插入 β 对话流。
    # β 本身无法"被 push 唤醒" — 需人工看到系统消息后向 β 提问。
    # 远期: 可将 alert 注入 β context, 触发自动处置建议生成。

    return {"status": "acknowledged", "code": code}
