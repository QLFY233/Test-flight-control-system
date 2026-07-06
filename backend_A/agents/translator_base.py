"""Abstract interface for trajectory translators.

Alpha implements this interface. Future small-model alpha
replaces the LLM implementation without changing the interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class TrajectoryTranslator(ABC):
    """Translates flight intent text into a TrajectorySpec dict."""

    @abstractmethod
    async def translate(self, intent: str, pose: Optional[dict] = None) -> dict:
        """Translate an intent string and current pose into a TrajectorySpec.

        Args:
            intent: Natural language flight intent (from beta or human).
            pose: Current drone pose dict {pos, quat, vel, ...} or None.

        Returns:
            TrajectorySpec dict with segments, constraints, etc.
        """
        ...


class TranslateError(Exception):
    """Raised when translation fails (LLM error, validation error, etc.)."""
    pass
