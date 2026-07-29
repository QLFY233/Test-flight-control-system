"""
统计分析工具 — 均值/方差/极值/趋势。纯 Python 实现。
"""
import math
import logging

logger = logging.getLogger(__name__)


class StatsAnalyzer:
    """统计分析器 — AnalyticsTool 接口。"""

    name = "stats"

    def handle(self, tool: str, args: dict) -> dict:
        if tool == "stats":
            return self.run(
                args.get("data", []),
                metric=args.get("metric", "all"),
            )
        return {"status": "error", "reason": f"unknown tool: {tool}"}

    def run(self, data: list, metric: str = "all") -> dict:
        """对时序数据执行统计分析。

        metric: "mean"|"variance"|"std"|"minmax"|"trend"|"all"
        """
        if not data:
            return {"status": "error", "reason": "empty data"}

        n = len(data)

        if metric in ("mean", "all"):
            mean_val = sum(data) / n
        if metric in ("variance", "std", "all"):
            mean_val = sum(data) / n
            var_val = sum((x - mean_val) ** 2 for x in data) / n
            std_val = math.sqrt(var_val)
        if metric in ("minmax", "all"):
            min_val = min(data)
            max_val = max(data)
            min_idx = data.index(min_val)
            max_idx = data.index(max_val)
        if metric in ("trend", "all"):
            # 简单线性趋势: 前半 vs 后半均值
            half = n // 2
            first_half_mean = sum(data[:half]) / half if half > 0 else data[0]
            second_half_mean = sum(data[half:]) / (n - half) if n > half else data[-1]

        result = {"n_samples": n}

        if metric in ("mean", "all"):
            result["mean"] = round(mean_val, 6)
        if metric in ("variance", "all"):
            result["variance"] = round(var_val, 6)
        if metric in ("std", "all"):
            result["std"] = round(std_val, 6)
        if metric in ("minmax", "all"):
            result["min"] = {"value": min_val, "index": min_idx}
            result["max"] = {"value": max_val, "index": max_idx}
            result["range"] = round(max_val - min_val, 6)
        if metric in ("trend", "all"):
            diff = second_half_mean - first_half_mean
            if abs(diff) < 0.001:
                direction = "stable"
            elif diff > 0:
                direction = "increasing"
            else:
                direction = "decreasing"
            result["trend"] = {
                "direction": direction,
                "first_half_mean": round(first_half_mean, 6),
                "second_half_mean": round(second_half_mean, 6),
                "change": round(diff, 6),
            }

        return {"status": "ok", **result}
