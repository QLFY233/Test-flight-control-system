"""
Detector interface and registry for the monitoring system.

Each detector inspects drone state (pose, velocity, trajectory status)
and returns a list of alert dicts when violations are detected.
"""

from abc import ABC, abstractmethod
from typing import Any


class Detector(ABC):
    """Abstract base for safety detectors."""

    name: str = "base"

    @abstractmethod
    def update(self, sample: Any, bstate: Any) -> list:
        """
        Inspect the current state and return alerts.

        Args:
            sample: Current TrajectorySample (or None if no active trajectory).
            bstate: BState instance with current pose, field config, etc.

        Returns:
            List of alert dicts. Each alert has:
              - code: str       (alert code, e.g. "out_of_boundary")
              - severity: str   ("warning" | "critical")
              - detail: str     (human-readable description)
              - timestamp: float (epoch seconds)
              - detector: str   (detector name)
        """
        ...


# Global detector registry
DETECTORS: list = []


def register_detector(detector: Detector) -> None:
    """Register a detector for use by the monitor component."""
    DETECTORS.append(detector)


def get_detectors() -> list:
    """Return all registered detectors."""
    return list(DETECTORS)


def clear_detectors() -> None:
    """Clear all registered detectors (useful in tests)."""
    DETECTORS.clear()


def _make_alert(code: str, severity: str, detail: str, detector_name: str) -> dict:
    """Create a standard alert dict."""
    import time
    return {
        "code": code,
        "severity": severity,
        "detail": detail,
        "timestamp": time.time(),
        "detector": detector_name,
    }
