"""
动作编码表 — 与总体架构 §2.2 一致 (schema_version=2)。
从 bus.protocol 导入 (backend-B/bus/protocol.py 软链→ shared/protocol.py)。
"""
from bus.protocol import (
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

VALID_ACTION_CODES = frozenset([
    ACTION_CODE_TAKEOFF,
    ACTION_CODE_LAND,
    ACTION_CODE_GOTO,
    ACTION_CODE_MOVE,
    ACTION_CODE_CLIMB,
    ACTION_CODE_DESCEND,
    ACTION_CODE_YAW,
    ACTION_CODE_HOVER,
    ACTION_CODE_RETURN_HOME,
])
