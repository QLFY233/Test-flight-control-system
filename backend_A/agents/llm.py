"""Agent factory for Pydantic AI.

Creates Agent instances with configurable providers.
Uses DeepSeek-V4-Flash (OpenAI-compatible) as the default.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel

logger = logging.getLogger(__name__)

PROVIDERS: dict[str, dict] = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "api_key_env": "DEEPSEEK_API_KEY",
        "model": "deepseek-chat",
    },
    # Add more OpenAI-compatible providers here
}


def make_agent(
    instructions: str,
    tools: Optional[list] = None,
    output_type: Optional[type] = None,
    provider: Optional[str] = None,
) -> Agent:
    """Create a Pydantic AI Agent with the given configuration.

    Args:
        instructions: System prompt / instructions string.
        tools: List of tool functions (for beta) or None (for alpha).
        output_type: Pydantic model for structured output (alpha uses TrajectorySpec).
        provider: Provider key in PROVIDERS dict (default: from LLM_PROVIDER env or "deepseek").

    Returns:
        Configured pydantic_ai.Agent instance.
    """
    provider_name = provider or os.environ.get("LLM_PROVIDER", "deepseek")
    if provider_name not in PROVIDERS:
        raise ValueError(
            f"Unknown LLM provider: {provider_name}. Available: {list(PROVIDERS.keys())}"
        )

    cfg = PROVIDERS[provider_name]
    api_key = os.environ.get(cfg["api_key_env"])
    if not api_key:
        raise RuntimeError(
            f"Environment variable '{cfg['api_key_env']}' is not set. "
            f"Required for provider '{provider_name}'."
        )

    model = OpenAIModel(
        cfg["model"],
        base_url=cfg["base_url"],
        api_key=api_key,
    )

    kwargs = dict(instructions=instructions)
    if tools:
        kwargs["tools"] = tools
    if output_type:
        kwargs["output_type"] = output_type

    agent = Agent(model, **kwargs)
    logger.info(
        f"agents/llm: created agent provider={provider_name} model={cfg['model']} "
        f"tools={len(tools) if tools else 0} output_type={output_type.__name__ if output_type else 'None'}"
    )
    return agent
