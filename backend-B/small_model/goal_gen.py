"""
GoalGenerator 统一接口 + 工厂函数。
端侧小模型: ActionCommand + 状态/环境 → 目标点。
先导用 stub, 阶段4 换 ONNX 推理。
"""
import os
from abc import ABC, abstractmethod


class GoalGenError(Exception):
    """目标点生成失败。"""
    pass


class GoalGenerator(ABC):
    """端侧小模型统一接口 (总体架构 §3.7 组件契约)。

    输入: 单条 ActionCommand + 当前位姿 + 离散环境 + safety_constraints
    输出: {"goal": [x,y,z], "yaw": float, "speed_max": float}
    失败抛 GoalGenError, 上层捕获后上行 reject 并兜底 hover。
    """

    @abstractmethod
    def generate(self, action: dict, pose: dict, env: dict, safety: dict) -> dict:
        """返回 {"goal": [x,y,z], "yaw": float, "speed_max": float}。

        action: {code, value?, target?, units?} (总体架构 §2.2 单条)
        pose: {pos: [x,y,z], quat: [w,x,y,z], vel: [...]}
        env: 离散环境 dict (先导 stub 忽略)
        safety: {speed_max, ceiling, floor, boundary: [[min],[max]]}
        """
        ...


def make_goal_generator() -> GoalGenerator:
    """工厂: 按 SMALL_MODEL_BACKEND 环境变量创建 GoalGenerator。"""
    backend = os.environ.get("SMALL_MODEL_BACKEND", "stub")
    if backend == "onnx":
        # 阶段4 ONNX 推理 (先导不实现)
        raise NotImplementedError("ONNX backend not yet implemented (stage 4)")
    # 默认 stub
    from .stub import StubGoalGenerator
    return StubGoalGenerator()
