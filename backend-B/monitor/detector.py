"""
监控检测器接口 + 注册表 (开放式架构)。
先导: 阈值检测 + 趋势检测; 后期可加 ML 检测器。
"""
import time
from abc import ABC, abstractmethod


class Detector(ABC):
    """监控检测器统一接口 (总体架构 §3.7)。

    每个检测周期调用 update(), 返回 0~N 条 alert 事件。
    """

    name: str = "base"

    @abstractmethod
    def update(self, sample: dict) -> list[dict]:
        """检测一个遥测样本, 返回 alert 事件列表。

        sample: {pos, vel, accel, angular_vel, ts, last_data_ts, current_action_index}
        返回: [{"level": "warning"|"critical", "code": "...", "detail": "...", "ts": float, "action_index": int}]
        """
        ...


# 检测器注册表 — 添加新检测器只需 append
DETECTORS: list[Detector] = []


def register(detector: Detector):
    DETECTORS.append(detector)


def get_all() -> list[Detector]:
    return list(DETECTORS)
