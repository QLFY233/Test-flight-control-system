"""
β Agent — 中枢大模型 (龙虾模式)。
人类唯一对话对象, 通过工具调度 α/analytics/历史查询等组件。
"""
import os
import logging
from .llm import make_agent

logger = logging.getLogger(__name__)


def _load_beta_prompt() -> str:
    """加载 β 系统 prompt。"""
    prompt_path = os.path.join(os.path.dirname(__file__), "..", "prompts", "beta.md")
    try:
        with open(prompt_path, "r") as f:
            return f.read()
    except FileNotFoundError:
        logger.warning(f"[beta] prompt file not found at {prompt_path}")
        return "你是试飞控制系统中枢大模型 β Agent。"


def create_beta_agent():
    """创建 β Agent 单例 — 带完整工具集。"""
    from tools.beta_tools import (
        # 实时状态
        get_field_map,
        get_current_pose,
        get_recent_telemetry,
        get_current_environment,
        # 历史查询
        query_sessions,
        query_telemetry,
        query_environment,
        query_conversations,
        # α 调度
        propose_to_alpha,
        forward_last_human_message,
        # analytics (stub)
        analytics_fft,
        analytics_stats,
        analytics_filter,
        # dashboard (stub)
        dashboard_configure,
        dashboard_set_filter,
        dashboard_list_panels,
    )

    tools = [
        get_field_map,
        get_current_pose,
        get_recent_telemetry,
        get_current_environment,
        query_sessions,
        query_telemetry,
        query_environment,
        query_conversations,
        propose_to_alpha,
        forward_last_human_message,
        analytics_fft,
        analytics_stats,
        analytics_filter,
        dashboard_configure,
        dashboard_set_filter,
        dashboard_list_panels,
    ]

    prompt = _load_beta_prompt()
    agent = make_agent(instructions=prompt, tools=tools)
    logger.info(f"[beta] agent created with {len(tools)} tools")
    return agent
