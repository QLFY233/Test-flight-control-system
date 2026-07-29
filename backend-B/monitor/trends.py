"""
趋势检测器 — 突变检测 + 持续偏离检测。
滑窗统计, 先导用纯 Python 计算 (不引入 numpy/scipy 做趋势)。
"""
from __future__ import annotations
import time
import logging
from collections import deque
from .detector import Detector

logger = logging.getLogger(__name__)

WINDOW_SIZE = 20  # 滑窗样本数 (10Hz → 2秒窗口)


class TrendDetector(Detector):
    """趋势检测器 — 突变 (二阶差分) + 持续偏离 (setpoint vs actual)。"""

    name = "trend"

    def __init__(self):
        self._speed_history: deque = deque(maxlen=WINDOW_SIZE)
        self._pos_history: deque = deque(maxlen=WINDOW_SIZE)

    def update(self, sample: dict) -> list[dict]:
        alerts = []
        ts = sample.get("ts", time.time())
        action_idx = sample.get("current_action_index", 0)

        vel = sample.get("vel", [0, 0, 0])
        pos = sample.get("pos", [0, 0, 0])
        speed = (vel[0] ** 2 + vel[1] ** 2 + vel[2] ** 2) ** 0.5

        self._speed_history.append(speed)
        self._pos_history.append(list(pos))

        # 突变检测: 相邻帧速度二阶差分超阈值 (抖动)
        if len(self._speed_history) >= 3:
            speeds = list(self._speed_history)
            accel1 = abs(speeds[-1] - speeds[-2])
            accel2 = abs(speeds[-2] - speeds[-3])
            jerk = abs(accel1 - accel2)  # 二阶差分 (加加速度)
            if jerk > 2.0:  # 阈值 m/s³
                alerts.append({
                    "level": "warning",
                    "code": "speed_jerk",
                    "detail": f"速度突变, jerk={jerk:.2f} m/s³",
                    "ts": ts, "action_index": action_idx,
                })

        # 持续偏离检测: 滑窗内位置变化超过预期
        if len(self._pos_history) >= WINDOW_SIZE:
            positions = list(self._pos_history)
            # 计算滑窗内的总位移
            first = positions[0]
            last = positions[-1]
            total_disp = ((last[0] - first[0]) ** 2 + (last[1] - first[1]) ** 2 + (last[2] - first[2]) ** 2) ** 0.5
            # 如果位移小但速度波动大 → 跟不住 (振荡)
            if total_disp < 0.1:  # 2秒内位移 < 0.1m
                speeds = list(self._speed_history)
                if speeds:
                    avg_speed = sum(speeds) / len(speeds)
                    if avg_speed > 0.3:  # 平均速度 > 0.3 m/s 但位移小 → 振荡
                        alerts.append({
                            "level": "warning",
                            "code": "tracking_oscillation",
                            "detail": f"位置振荡, avg_speed={avg_speed:.2f} m/s, displacement={total_disp:.2f}m",
                            "ts": ts, "action_index": action_idx,
                        })

        return alerts
