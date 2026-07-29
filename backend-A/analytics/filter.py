"""
数字滤波工具 — 移动平均/低通/高通。纯 Python 实现。
"""
import math
import logging

logger = logging.getLogger(__name__)


class FilterTool:
    """数字滤波器 — AnalyticsTool 接口。"""

    name = "filter"

    def handle(self, tool: str, args: dict) -> dict:
        if tool == "filter":
            return self.run(
                args.get("data", []),
                filter_type=args.get("type", "moving_average"),
                params=args.get("params", {}),
            )
        return {"status": "error", "reason": f"unknown tool: {tool}"}

    def run(self, data: list, filter_type: str = "moving_average", params: dict | None = None) -> dict:
        """对时序数据执行滤波。

        filter_type: "moving_average"|"lowpass"|"highpass"
        params: {window?: int, cutoff?: float, sample_rate?: float}
        """
        if not data:
            return {"status": "error", "reason": "empty data"}

        p = params or {}

        if filter_type == "moving_average":
            return self._moving_average(data, p.get("window", 5))
        elif filter_type == "lowpass":
            return self._lowpass(data, p.get("cutoff", 1.0), p.get("sample_rate", 10.0))
        elif filter_type == "highpass":
            return self._highpass(data, p.get("cutoff", 1.0), p.get("sample_rate", 10.0))
        else:
            return {"status": "error", "reason": f"unknown filter type: {filter_type}"}

    def _moving_average(self, data: list, window: int) -> dict:
        """滑动窗口平均。"""
        window = min(window, len(data))
        if window <= 1:
            return {"status": "ok", "filtered": data, "window": window}

        result = []
        half = window // 2
        for i in range(len(data)):
            start = max(0, i - half)
            end = min(len(data), i + window - half)
            subset = data[start:end]
            result.append(round(sum(subset) / len(subset), 6))

        return {"status": "ok", "filtered": result, "window": window, "n": len(result)}

    def _lowpass(self, data: list, cutoff: float, sample_rate: float) -> dict:
        """一阶低通滤波器: y[i] = α * x[i] + (1-α) * y[i-1]。"""
        dt = 1.0 / sample_rate
        rc = 1.0 / (2.0 * math.pi * cutoff)
        alpha = dt / (rc + dt) if rc + dt > 0 else 0.5

        result = [data[0]]
        for i in range(1, len(data)):
            result.append(round(alpha * data[i] + (1 - alpha) * result[-1], 6))

        return {
            "status": "ok",
            "filtered": result,
            "cutoff": cutoff,
            "alpha": round(alpha, 4),
            "n": len(result),
        }

    def _highpass(self, data: list, cutoff: float, sample_rate: float) -> dict:
        """一阶高通滤波器: y[i] = α * (y[i-1] + x[i] - x[i-1])。"""
        dt = 1.0 / sample_rate
        rc = 1.0 / (2.0 * math.pi * cutoff)
        alpha = rc / (rc + dt) if rc + dt > 0 else 0.5

        result = [0.0]
        for i in range(1, len(data)):
            result.append(round(alpha * (result[-1] + data[i] - data[i - 1]), 6))

        return {
            "status": "ok",
            "filtered": result,
            "cutoff": cutoff,
            "alpha": round(alpha, 4),
            "n": len(result),
        }
