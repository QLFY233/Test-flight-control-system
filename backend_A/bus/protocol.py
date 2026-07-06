"""Protocol constants shared between A and B sides.

Must be kept in sync with backend-B/bus/protocol.py.
"""

# Schema version — bump on any field semantic change
SCHEMA_VERSION = 1

# msgpack serialization
MSGPACK_USE_BIN_TYPE = True

# Message types (msg_type field)
MSG_CALL = "call"
MSG_RESULT = "result"
MSG_EVENT = "event"
MSG_ERROR = "error"

# A→B call tools (frozen, see A-B interface doc)
TOOL_TRANSLATE = "translate"
TOOL_TRAJECTORY = "trajectory"
TOOL_ABORT = "abort"
TOOL_HOVER = "hover"

# Heartbeat tools
TOOL_PING = "ping"
TOOL_PONG = "pong"

# B→A event tools (frozen)
TOOL_POSE = "pose"
TOOL_TELEMETRY = "telemetry"
TOOL_STATUS = "status"
TOOL_REJECT = "reject"
TOOL_ALERT = "alert"

# Component names (for bus routing)
COMP_ALPHA = "alpha"
COMP_BETA = "beta"
COMP_SOLVER = "solver"
COMP_MONITOR = "monitor"
COMP_HEARTBEAT = "heartbeat"

# All valid "to" targets for bus routing
VALID_TARGETS = {
    COMP_ALPHA,
    COMP_BETA,
    COMP_SOLVER,
    COMP_MONITOR,
    COMP_HEARTBEAT,
    "fft_analyzer",
    "stats_analyzer",
    "filter_analyzer",
}
