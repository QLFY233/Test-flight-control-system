"""Filter tools — lowpass, highpass, moving average for time series."""

from __future__ import annotations

import math
from typing import Any


class FilterTool:
    """Apply digital filters to a time series."""

    def analyze(self, data: list[float], params: dict) -> dict:
        """Apply a filter to data.

        Args:
            data: List of float values.
            params: {
                "filter_type": "lowpass" | "highpass" | "moving_average",
                "cutoff": float (normalized 0-0.5, for lowpass/highpass),
                "window_size": int (for moving_average, default 5),
            }

        Returns:
            dict with filtered data, original length, filter info.
        """
        if not data:
            return {"error": "no data provided"}

        filter_type = params.get("filter_type", "moving_average")
        cutoff = params.get("cutoff", 0.2)
        window_size = params.get("window_size", 5)

        if filter_type == "moving_average":
            filtered = self._moving_average(data, window_size)
        elif filter_type == "lowpass":
            filtered = self._lowpass(data, cutoff)
        elif filter_type == "highpass":
            filtered = self._highpass(data, cutoff)
        else:
            return {"error": f"unknown filter_type: {filter_type}"}

        return {
            "filter_type": filter_type,
            "original_length": len(data),
            "filtered_length": len(filtered),
            "params": {"cutoff": cutoff, "window_size": window_size},
            "data": [round(x, 6) for x in filtered[:500]],  # limit for context
        }

    def _moving_average(self, data: list[float], window: int) -> list[float]:
        """Simple moving average filter."""
        if window < 1:
            window = 1
        half = window // 2
        n = len(data)
        result = []
        for i in range(n):
            start = max(0, i - half)
            end = min(n, i + half + 1)
            window_data = data[start:end]
            result.append(sum(window_data) / len(window_data))
        return result

    def _lowpass(self, data: list[float], cutoff: float) -> list[float]:
        """Simple first-order lowpass filter.

        y[n] = alpha * x[n] + (1-alpha) * y[n-1]
        alpha = cutoff (simplified, for low cutoff = more smoothing)
        """
        if not 0 < cutoff <= 1:
            cutoff = 0.2
        filtered = [data[0]]
        for x in data[1:]:
            filtered.append(cutoff * x + (1 - cutoff) * filtered[-1])
        return filtered

    def _highpass(self, data: list[float], cutoff: float) -> list[float]:
        """Simple first-order highpass filter.

        y[n] = alpha * (y[n-1] + x[n] - x[n-1])
        alpha = 1 - cutoff (simplified)
        """
        if not 0 < cutoff <= 1:
            cutoff = 0.2
        alpha = 1.0 - cutoff
        filtered = [0.0]
        for i in range(1, len(data)):
            filtered.append(alpha * (filtered[-1] + data[i] - data[i - 1]))
        return filtered
