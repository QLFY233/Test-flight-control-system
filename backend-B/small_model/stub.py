"""
先导 stub — 规则映射动作编码 → 目标点 (不训练, 打通链路)。
9 类动作编码映射 + boundary/ceiling/floor/speed_max 夹紧。
未知编码抛 GoalGenError → 上行 reject。
"""
import math
from .action_codes import (
    ACTION_CODE_TAKEOFF,
    ACTION_CODE_LAND,
    ACTION_CODE_GOTO,
    ACTION_CODE_MOVE,
    ACTION_CODE_CLIMB,
    ACTION_CODE_DESCEND,
    ACTION_CODE_YAW,
    ACTION_CODE_HOVER,
    ACTION_CODE_RETURN_HOME,
)
from .goal_gen import GoalGenerator, GoalGenError


def _clamp(val, lo, hi):
    return max(lo, min(hi, val))


def _clamp_point(x, y, z, boundary):
    """将 (x, y, z) 夹紧到 boundary 内最近点。"""
    bx = boundary[0]
    bx_max = boundary[1]
    return (
        _clamp(x, bx[0], bx_max[0]),
        _clamp(y, bx[1], bx_max[1]),
        _clamp(z, bx[2], bx_max[2]),
    )


class StubGoalGenerator(GoalGenerator):
    """先导规则占位: 按动作编码表硬编码映射 (B spec §4.2)。"""

    def generate(self, action: dict, pose: dict, env: dict, safety: dict) -> dict:
        code = action.get("code", "")

        cur = pose.get("pos", [0, 0, 0])
        cur_x, cur_y, cur_z = cur[0], cur[1], cur[2]
        yaw = pose.get("yaw", 0.0)

        b = safety.get("boundary", [[0, 0, 0], [5, 4, 3]])
        ceiling = safety.get("ceiling", 2.5)
        floor = safety.get("floor", 0.3)
        speed_max = safety.get("speed_max", 1.5)

        # home 位置从默认约束 (field.home)
        # 从当前类的 home 属性获取 (由 component 注入)
        home = getattr(self, "_home", [0, 0, 0.5])

        if code == ACTION_CODE_GOTO:
            target = action.get("target", cur)
            goal = list(_clamp_point(target[0], target[1], target[2], b))
            goal[2] = _clamp(goal[2], floor, ceiling)
            out_yaw = action.get("yaw", yaw)

        elif code == ACTION_CODE_TAKEOFF:
            value = action.get("value", 1.0)
            goal = list(_clamp_point(home[0], home[1], value, b))
            goal[2] = _clamp(value, floor, ceiling)
            out_yaw = yaw

        elif code == ACTION_CODE_LAND:
            goal = list(_clamp_point(home[0], home[1], floor, b))
            out_yaw = yaw

        elif code == ACTION_CODE_MOVE:
            value = action.get("value", 1.0)
            direction = action.get("target")  # 可选方向单位向量
            if direction and len(direction) == 3:
                dx, dy, dz = direction[0], direction[1], direction[2]
            else:
                dx = math.cos(yaw)
                dy = math.sin(yaw)
                dz = 0.0
            mag = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
            nx, ny, nz = dx / mag, dy / mag, dz / mag
            gx = cur_x + nx * value
            gy = cur_y + ny * value
            gz = cur_z + nz * value
            goal = list(_clamp_point(gx, gy, gz, b))
            goal[2] = _clamp(goal[2], floor, ceiling)
            out_yaw = action.get("yaw", yaw)

        elif code == ACTION_CODE_CLIMB:
            value = action.get("value", 0.5)
            gz = _clamp(cur_z + value, floor, ceiling)
            goal = list(_clamp_point(cur_x, cur_y, gz, b))
            goal[2] = gz  # z 只受 floor/ceiling 限制
            out_yaw = yaw

        elif code == ACTION_CODE_DESCEND:
            value = action.get("value", 0.5)
            gz = _clamp(cur_z - value, floor, ceiling)
            goal = list(_clamp_point(cur_x, cur_y, gz, b))
            goal[2] = gz
            out_yaw = yaw

        elif code == ACTION_CODE_YAW:
            value = action.get("value", 0.0)
            goal = list(cur)  # 不动位置
            out_yaw = math.radians(value) if action.get("units") == "deg" else value

        elif code == ACTION_CODE_HOVER:
            goal = list(cur)
            out_yaw = yaw

        elif code == ACTION_CODE_RETURN_HOME:
            goal = list(_clamp_point(home[0], home[1], home[2], b))
            goal[2] = _clamp(goal[2], floor, ceiling)
            out_yaw = 0.0

        else:
            raise GoalGenError(f"unknown_action_code:{code}")

        # 最终校验: 夹紧后仍越界 → reject
        gx_c, gy_c, gz_c = _clamp_point(goal[0], goal[1], goal[2], b)
        if abs(gx_c - goal[0]) > 0.001 or abs(gy_c - goal[1]) > 0.001 or abs(gz_c - goal[2]) > 0.001:
            raise GoalGenError("out_of_boundary_after_clamp")

        return {"goal": goal, "yaw": out_yaw, "speed_max": speed_max}
