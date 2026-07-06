"""Component registry for the internal message bus.

Components register themselves at startup with their accepted tools.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_registry: dict[str, dict[str, Any]] = {}


def register(name: str, component: Any, tools: list[str] | None = None) -> None:
    """Register a component with its accepted tool names."""
    _registry[name] = {
        "instance": component,
        "tools": set(tools or []),
    }
    logger.info(f"bus/registry: registered component '{name}' tools={list(_registry[name]['tools'])}")


def unregister(name: str) -> None:
    """Remove a component from the registry."""
    _registry.pop(name, None)
    logger.info(f"bus/registry: unregistered '{name}'")


def get(name: str) -> dict[str, Any] | None:
    """Get a registered component by name."""
    return _registry.get(name)


def list_all() -> list[str]:
    """Return names of all registered components."""
    return list(_registry.keys())


def accepts(name: str, tool: str) -> bool:
    """Check whether a component accepts a given tool."""
    entry = _registry.get(name)
    if entry is None:
        return False
    return tool in entry["tools"]


def get_instance(name: str) -> Any | None:
    """Get the component instance."""
    entry = _registry.get(name)
    if entry is None:
        return None
    return entry["instance"]
