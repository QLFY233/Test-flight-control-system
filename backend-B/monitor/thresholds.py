"""
阈值检测器 — 预设阈值检查 (速度/高度/加速度/角速度/数据停产/boundary)。
位置超 boundary 为软告警, 不自动终止飞行。
"""
from __future__ import annotations
import time
import logging
from .detector import Detector

logger = logging.getLogger(__name__)


class ThresholdDetector(Detector):
    """阈值检测器 — 检查遥测是否超过 safety_constraints。"""

    name = "threshold"

    def __init__(self, field: dict, constraints: dict, boundary_margin: float = 0.5):
        self._field = field
        g = constraints.get("global", {})
        self._speed_max = g.get("speed_max", 1.5)
        self._ceiling = g.get("ceiling", 2.5)
        self._floor = g.get("floor", 0.3)
        self._accel_max = g.get("accel_max", 2.0)
        self._angular_max = g.get("angular_velocity_max", 0.5)
        # boundary 来自 field
        b = field.get("boundary", {})
        self._bx = b.get("x", [0, 5])
        self._by = b.get("y", [0, 4])
        self._bz = b.get("z", [0, 3])
        # 软告警边界容差 (PX4 适配 2026-08-03): PX4 home 位于 Gazebo 原点 =
        # field boundary 角点, 悬停/噪声使坐标轻微负值 → out_of_boundary 常亮
        # 误报。软告警 (不终止飞行) 容忍 margin 内越界, 硬夹紧仍由 small_model
        # stub 按原 boundary 执行 (零改动)。
        self._boundary_margin = boundary_margin

    def update(self, sample: dict) -> list[dict]:
        alerts = []
        ts = sample.get("ts", time.time())
        action_idx = sample.get("current_action_index", 0)

        # B-5: 尚未收到首帧无人机数据时不评估 — 启动阶段 vel/accel/pos 全为默认零值,
        # 会刷出 floor_breach / drone_data_stale 假阳性。默认 True 兼容直接调用方。
        if not sample.get("data_received", True):
            return alerts

        vel = sample.get("vel", [0, 0, 0])
        speed = (vel[0] ** 2 + vel[1] ** 2 + vel[2] ** 2) ** 0.5
        pos = sample.get("pos", [0, 0, 0])
        accel = sample.get("accel", [0, 0, 0])
        angular = sample.get("angular_vel", [0, 0, 0])

        # 速度检测
        if speed > self._speed_max:
            alerts.append({
                "level": "warning",
                "code": "overspeed",
                "detail": f"速度 {speed:.2f} m/s 超过限制 {self._speed_max} m/s",
                "ts": ts, "action_index": action_idx,
            })

        # 高度检测
        z = pos[2] if len(pos) > 2 else 0.0
        if z > self._ceiling:
            alerts.append({
                "level": "warning",
                "code": "ceiling_breach",
                "detail": f"高度 {z:.2f} m 超过上限 {self._ceiling} m",
                "ts": ts, "action_index": action_idx,
            })
        # B-5: z≤1cm 视为停机坪常态 (起飞前/降落在地面), 不报 floor_breach
        # PX4 适配 (2026-08-03): SITL 地面 z 噪声到 ~3cm, 豁免提到 5cm
        if z < self._floor and z > 0.05:
            alerts.append({
                "level": "warning",
                "code": "floor_breach",
                "detail": f"高度 {z:.2f} m 低于下限 {self._floor} m",
                "ts": ts, "action_index": action_idx,
            })

        # 加速度检测
        acc_mag = (accel[0] ** 2 + accel[1] ** 2 + accel[2] ** 2) ** 0.5
        if acc_mag > self._accel_max:
            alerts.append({
                "level": "warning",
                "code": "overaccel",
                "detail": f"加速度 {acc_mag:.2f} m/s² 超过限制 {self._accel_max} m/s²",
                "ts": ts, "action_index": action_idx,
            })

        # 角速度检测
        ang_mag = (angular[0] ** 2 + angular[1] ** 2 + angular[2] ** 2) ** 0.5
        if ang_mag > self._angular_max:
            alerts.append({
                "level": "warning",
                "code": "over_angular",
                "detail": f"角速度 {ang_mag:.2f} rad/s 超过限制 {self._angular_max} rad/s",
                "ts": ts, "action_index": action_idx,
            })

        # 位置超 boundary (软告警 — 不终止飞行; margin 内容忍, 见 __init__ 注释)
        x, y = pos[0], pos[1]
        m = self._boundary_margin
        if not (self._bx[0] - m <= x <= self._bx[1] + m
                and self._by[0] - m <= y <= self._by[1] + m):
            alerts.append({
                "level": "warning",
                "code": "out_of_boundary",
                "detail": f"位置 ({x:.2f}, {y:.2f}) 超出场地边界 (margin {m:.1f}m)",
                "ts": ts, "action_index": action_idx,
            })

        # 数据停产检测
        last_ts = sample.get("last_data_ts", ts)
        if ts - last_ts > 0.5:
            alerts.append({
                "level": "critical",
                "code": "drone_data_stale",
                "detail": f"无人机数据停产 {ts - last_ts:.1f}s",
                "ts": ts, "action_index": action_idx,
            })

        if alerts:
            logger.info(f"[thresholds] {len(alerts)} alert(s): {[a['code'] for a in alerts]}")

        return alerts
