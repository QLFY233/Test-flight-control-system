"""
Protocol constants shared between Backend A and Backend B.
Mirrors backend-A/bus/protocol.py exactly.
"""

# Schema / wire format
SCHEMA_VERSION = 1
MSGPACK_USE_BIN_TYPE = True

# Message types
MSG_CALL = "call"
MSG_RESULT = "result"
MSG_EVENT = "event"
MSG_ERROR = "error"

# Tool names (A→B RPC tools)
TOOL_TRAJECTORY = "trajectory"
TOOL_ABORT = "abort"
TOOL_HOVER = "hover"
TOOL_PING = "ping"
TOOL_PONG = "pong"
TOOL_POSE = "pose"
TOOL_TELEMETRY = "telemetry"
TOOL_STATUS = "status"
TOOL_REJECT = "reject"
TOOL_ALERT = "alert"

# Component IDs
COMP_SOLVER = "solver"
COMP_MONITOR = "monitor"
COMP_HEARTBEAT = "heartbeat"

# All known tools (for validation)
KNOWN_TOOLS = {
    TOOL_TRAJECTORY,
    TOOL_ABORT,
    TOOL_HOVER,
    TOOL_PING,
    TOOL_PONG,
    TOOL_POSE,
    TOOL_TELEMETRY,
    TOOL_STATUS,
    TOOL_REJECT,
    TOOL_ALERT,
}

# MIME / content types
CONTENT_JSON = "application/json"
CONTENT_MSGPACK = "application/x-msgpack"
CONTENT_TEXT = "text/plain"
