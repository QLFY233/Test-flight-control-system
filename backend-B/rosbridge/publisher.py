"""
目标点发布器 — 20Hz 线程, 从 small_model 读当前目标点, 限速下发 setpoint。
首帧前填当前位置防跳变; 到达阈值自动切下条动作。
"""
from __future__ import annotations
import math
import time
import threading
import logging

from small_model.component import yaw_from_quat

logger = logging.getLogger(__name__)


class GoalPublisher:
    """目标点线程: 定频读取 small_model 的当前目标点, 下发 setpoint。"""

    def __init__(self, state, component, adapter, rate: float = 20.0):
        self._state = state
        self._component = component
        self._adapter = adapter
        self._rate = rate
        self._period = 1.0 / rate
        self._running = False
        self._thread: threading.Thread | None = None
        # 限速推进 (2026-08-03 S8.3b 根因修复):
        #   _ramp_pos/_ramp_key — 每个新目标从当前位置起坡, 沿目标方向按
        #   speed_max*dt 推进, 以"上一帧 setpoint"为锚而非"当前位姿"。
        #   旧实现每帧 set = cur + step: setpoint 永远只领先无人机一步,
        #   漂移力大于该误差纠正力时 setpoint 跟着无人机走, 目标永不可达
        #   (实测: 无人机 7cm/s 漂离原点, takeoff 目标 (0,0,1.0) 永不追踪)。
        #   _hold_point — hover 捕获一次当前位置后锁定发布 (零恢复力→自由漂移)。
        self._ramp_pos: list | None = None
        self._ramp_key = None
        self._hold_point: list | None = None

    def start(self):
        """启动目标点发布线程。"""
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="goal-publisher", daemon=True)
        self._thread.start()
        logger.info(f"[goal-publisher] started at {self._rate}Hz")

    def stop(self):
        """停止发布线程。

        注意: 本方法只 join 线程、不发最后一帧悬停 — 实际悬停由
        lifecycle._shutdown 的 bus hover 兜底 (B-13)。"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        logger.info("[goal-publisher] stopped")

    def _loop(self):
        """发布主循环。"""
        while self._running:
            start = time.time()
            try:
                self._tick()
            except Exception as e:
                logger.error(f"[goal-publisher] tick error: {e}")
            elapsed = time.time() - start
            sleep_time = max(0, self._period - elapsed)
            time.sleep(sleep_time)

    def _tick(self):
        """单次 tick: 读取目标点 → 限速 → 下发 setpoint。"""
        goal = self._component.get_current_goal()
        if goal is None:
            # 无目标: 下发悬停 (锁定保持点, 不随位姿重锚 — 修复自由漂移)
            self._publish_hover()
            return

        target = goal["goal"]
        yaw = goal.get("yaw", 0.0)
        speed_max = goal.get("speed_max", 1.5)
        key = (tuple(target), yaw)

        # 新目标: 从当前位置起坡 (防跳变), 并失效旧 hover 保持点
        if key != self._ramp_key:
            with self._state.pose_lock:
                cur_x, cur_y, cur_z = self._state._pose.pos[:3]
            self._ramp_pos = [cur_x, cur_y, cur_z]
            self._ramp_key = key
            self._hold_point = None
            self._hold_point = None

        # 限速: 沿"上一帧 setpoint→目标"方向推进不超过 speed_max*dt
        rx, ry, rz = self._ramp_pos
        dx = target[0] - rx
        dy = target[1] - ry
        dz = target[2] - rz
        dist = (dx * dx + dy * dy + dz * dz) ** 0.5

        step = speed_max * self._period
        if dist <= step:
            self._ramp_pos = list(target)
        else:
            ratio = step / dist
            self._ramp_pos = [rx + dx * ratio, ry + dy * ratio, rz + dz * ratio]

        self._adapter.publish_position(self._ramp_pos, yaw)

        # 到达检测用实际位姿 (而非 setpoint)
        with self._state.pose_lock:
            cur_x, cur_y, cur_z = self._state._pose.pos[:3]
        dcur = ((target[0] - cur_x) ** 2 + (target[1] - cur_y) ** 2 + (target[2] - cur_z) ** 2) ** 0.5
        if dcur < 0.15:
            self._component.check_arrival_and_advance([cur_x, cur_y, cur_z])

    def _publish_hover(self):
        """下发悬停: 捕获一次当前位置后锁定发布 (零恢复力→自由漂移修复)。"""
        # 2026-08-04: 无人机显著下降到保持点以下 (如"降落"后 z 从 1m→地面) → 重置保持点,
        # 避免 stale hold_point 让降落后的无人机立刻回飞 (配合 adapter 落地后重新武装)。
        try:
            with self._state.pose_lock:
                cur_pos = self._state._pose.pos[:3]
        except Exception:
            cur_pos = None
        if self._hold_point is not None and cur_pos is not None and cur_pos[2] < self._hold_point[2] - 0.7:
            logger.info("[goal-publisher] drone descended below hold point — resetting hover hold point")
            self._hold_point = None
        if self._hold_point is None:
            try:
                with self._state.pose_lock:
                    self._hold_point = self._state._pose.pos[:3]
            except Exception:
                self._hold_point = [0.0, 0.0, 0.5]
            logger.info(f"[goal-publisher] hover hold point set: {[round(v, 2) for v in self._hold_point]}")
        try:
            with self._state.pose_lock:
                quat = self._state._pose.quat[:]
        except Exception:
            quat = [1.0, 0.0, 0.0, 0.0]

        yaw = yaw_from_quat(quat)
        self._adapter.publish_position(self._hold_point, yaw)
