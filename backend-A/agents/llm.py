"""
LLM Agent 工厂 — 多 provider 可扩展。
切 provider 只改 LLM_PROVIDER 环境变量。
使用 pydantic-ai 2.0 API。
"""
import os
import logging
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

logger = logging.getLogger(__name__)

PROVIDERS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "api_key_env": "DEEPSEEK_API_KEY",
        "model": "deepseek-chat",
    },
}


def _get_provider_cfg() -> dict:
    provider = os.environ.get("LLM_PROVIDER", "deepseek")
    if provider not in PROVIDERS:
        raise ValueError(
            f"Unknown LLM_PROVIDER '{provider}'. Available: {list(PROVIDERS.keys())}"
        )
    return PROVIDERS[provider]


def make_agent(instructions: str, tools: list = None, output_type=None) -> Agent:
    """创建 LLM Agent。

    Args:
        instructions: 系统 prompt
        tools: 工具函数列表 (可选)
        output_type: 结构化输出类型 (Pydantic model, 可选)
    """
    cfg = _get_provider_cfg()
    api_key = os.environ.get(cfg["api_key_env"], "")

    if not api_key:
        logger.warning(
            f"[llm] {cfg['api_key_env']} not set — "
            f"LLM calls will fail. Set it in .env or environment."
        )

    provider = OpenAIProvider(base_url=cfg["base_url"], api_key=api_key)
    model = OpenAIChatModel(cfg["model"], provider=provider)

    agent = Agent(
        model,
        instructions=instructions,
        tools=tools or [],
        output_type=output_type or str,  # 默认 str (文本输出)
    )

    logger.info(
        f"[llm] agent created: provider={os.environ.get('LLM_PROVIDER', 'deepseek')}, "
        f"model={cfg['model']}"
    )
    return agent
