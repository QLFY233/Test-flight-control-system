"""
目标点发布器 — 20Hz 线程, 从 small_model 读当前目标点, 限速下发 setpoint。
首帧前填当前位置防跳变; 到达阈值自动切下条动作。
"""
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
        # 首帧标志: 防跳变
        self._first_frame = True

    def start(self):
        """启动目标点发布线程。"""
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="goal-publisher", daemon=True)
        self._thread.start()
        logger.info(f"[goal-publisher] started at {self._rate}Hz")

    def stop(self):
        """停止发布线程, 发最后一帧悬停。"""
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
            # 无目标: 下发悬停 (当前位置)
            self._publish_hover()
            return

        target = goal["goal"]
        yaw = goal.get("yaw", 0.0)
        speed_max = goal.get("speed_max", 1.5)

        # 当前位置
        with self._state.pose_lock:
            cur_x, cur_y, cur_z = (
                self._state._pose.pos[0],
                self._state._pose.pos[1],
                self._state._pose.pos[2],
            )

        # 首帧防跳变: 先填当前位置
        if self._first_frame:
            self._adapter.publish_position([cur_x, cur_y, cur_z], yaw)
            self._first_frame = False
            return

        # 限速: 目标点不一次性跳到, 沿方向移动不超过 speed_max * dt
        dx = target[0] - cur_x
        dy = target[1] - cur_y
        dz = target[2] - cur_z
        dist = (dx * dx + dy * dy + dz * dz) ** 0.5

        step = speed_max * self._period
        if dist <= step:
            set_x, set_y, set_z = target[0], target[1], target[2]
        else:
            ratio = step / dist
            set_x = cur_x + dx * ratio
            set_y = cur_y + dy * ratio
            set_z = cur_z + dz * ratio

        self._adapter.publish_position([set_x, set_y, set_z], yaw)

        # 到达检测
        if dist < 0.15:
            self._component.check_arrival_and_advance([cur_x, cur_y, cur_z])

    def _publish_hover(self):
        """下发悬停 (当前位姿)。"""
        try:
            with self._state.pose_lock:
                px, py, pz = (
                    self._state._pose.pos[0],
                    self._state._pose.pos[1],
                    self._state._pose.pos[2],
                )
                quat = self._state._pose.quat[:]
        except Exception:
            px, py, pz = 0.0, 0.0, 0.5
            quat = [1.0, 0.0, 0.0, 0.0]

        yaw = yaw_from_quat(quat)
        self._adapter.publish_position([px, py, pz], yaw)
