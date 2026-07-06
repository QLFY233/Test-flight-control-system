"""
Component registry for Backend B bus architecture.

All components (solver, monitor, heartbeat, etc.) register themselves
on startup so the IPC router can dispatch incoming messages.
"""

from typing import Any, Optional

_registry: dict = {}

def register(name: str, component: Any) -> None:
    """Register a bus component by name."""
    _registry[name] = component

def get(name: str) -> Optional[Any]:
    """Retrieve a registered component by name, or None."""
    return _registry.get(name)

def unregister(name: str) -> None:
    """Remove a component from the registry."""
    _registry.pop(name, None)

def list_registered() -> list:
    """Return names of all registered components."""
    return list(_registry.keys())

def clear() -> None:
    """Clear all registrations (useful in tests)."""
    _registry.clear()
