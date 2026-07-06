"""Statistical analysis tool — mean, variance, extrema, trend."""

from __future__ import annotations

import math
from typing import Any


class StatsTool:
    """Compute basic statistics on a time series."""

    def analyze(self, data: list[float], params: dict) -> dict:
        """Compute statistical measures.

        Args:
            data: List of float values.
            params: {} (reserved for future)

        Returns:
            dict with mean, variance, std, min, max, range, trend, etc.
        """
        if not data:
            return {"error": "no data provided"}

        n = len(data)
        if n == 0:
            return {"error": "empty data"}

        mean = sum(data) / n
        variance = sum((x - mean) ** 2 for x in data) / n
        std = math.sqrt(variance)

        sorted_data = sorted(data)
        minimum = sorted_data[0]
        maximum = sorted_data[-1]
        data_range = maximum - minimum

        # Median
        if n % 2 == 0:
            median = (sorted_data[n // 2 - 1] + sorted_data[n // 2]) / 2
        else:
            median = sorted_data[n // 2]

        # Trend (simple linear regression slope)
        x_mean = (n - 1) / 2.0
        y_mean = mean
        numerator = sum((i - x_mean) * (data[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        trend = numerator / denominator if denominator != 0 else 0.0

        # Trend direction
        if trend > 0.001:
            trend_desc = "increasing"
        elif trend < -0.001:
            trend_desc = "decreasing"
        else:
            trend_desc = "stable"

        # RMS
        rms = math.sqrt(sum(x ** 2 for x in data) / n)

        # First and last values
        first = data[0]
        last = data[-1]

        return {
            "n": n,
            "mean": round(mean, 6),
            "variance": round(variance, 6),
            "std": round(std, 6),
            "min": round(minimum, 6),
            "max": round(maximum, 6),
            "range": round(data_range, 6),
            "median": round(median, 6),
            "rms": round(rms, 6),
            "first": round(first, 6),
            "last": round(last, 6),
            "trend_slope": round(trend, 8),
            "trend": trend_desc,
        }
