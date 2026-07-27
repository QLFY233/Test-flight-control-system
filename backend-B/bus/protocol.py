"""
A-B 跨进程协议常量 — 两侧逐字一致。
与 docs/specs/总体/2026-07-05-A-B-接口冻结.md 绑定，变更必须升级 SCHEMA_VERSION。
"""

# ── 协议版本 ──
SCHEMA_VERSION = 2  # 2026-07-07: 求解器路径废弃，改端侧小模型；trajectory→action

# ── msgpack 跨版本硬契约 ──
MSGPACK_USE_BIN_TYPE = True  # 两侧 Packer(unpackb) 必须一致

# ── IPC 传输层 ──
IPC_SOCKET_PATH = "/tmp/flight_control_AB.sock"
IPC_FRAME_MAX_BYTES = 16 * 1024 * 1024  # 16 MiB 上限，防 OOM
IPC_PING_INTERVAL = 2.0                 # A 侧 ping 间隔 (s)
IPC_PONG_TIMEOUT = 5.0                  # A 侧 pong 超时即断连 (s)
IPC_RECONNECT_INTERVAL = 1.0            # B 侧重连间隔 (s)

# ── 消息类型 ──
MSG_TYPE_CALL   = "call"
MSG_TYPE_RESULT = "result"
MSG_TYPE_EVENT  = "event"
MSG_TYPE_ERROR  = "error"

# ── to 组件名 ──
# A 内 / B 内通用
TO_ALPHA        = "alpha"
TO_BETA         = "beta"
TO_SMALL_MODEL  = "small_model"
TO_EGO_PLANNER  = "ego_planner"   # 阶段2/4
TO_LIDAR        = "lidar"         # 阶段2/4
TO_MONITOR      = "monitor"
TO_HEARTBEAT    = "heartbeat"     # pong 心跳特例
TO_BROADCAST    = "broadcast"

# A 侧 analytics 组件
TO_FFT_ANALYZER     = "fft_analyzer"
TO_STATS            = "stats"
TO_FILTER           = "filter"
TO_HISTORY_QUERY    = "history_query"
TO_DASHBOARD_DRIVER = "dashboard_driver"

# ── A→B call.tool 枚举 (冻结) ──
CALL_TOOL_ACTION = "action"   # ActionCommand 下发 (替代旧 trajectory)
CALL_TOOL_ABORT  = "abort"    # 中止当前动作序列
CALL_TOOL_HOVER  = "hover"    # 安全悬停
CALL_TOOL_PING   = "ping"     # 心跳

# ── B→A event.tool 枚举 (冻结) ──
EVENT_TOOL_POSE      = "pose"       # 位姿 10Hz
EVENT_TOOL_TELEMETRY = "telemetry"  # 富 IMU 10Hz (不入前端)
EVENT_TOOL_STATUS    = "status"     # 任务进度
EVENT_TOOL_REJECT    = "reject"     # 小模型/ego-planner 不可达
EVENT_TOOL_PONG      = "pong"       # 心跳回应
EVENT_TOOL_ALERT     = "alert"      # 监控异常

# ── 动作编码表 (ActionCommand.code) ──
ACTION_CODE_TAKEOFF     = "takeoff"
ACTION_CODE_LAND        = "land"
ACTION_CODE_GOTO        = "goto"
ACTION_CODE_MOVE        = "move"
ACTION_CODE_CLIMB       = "climb"
ACTION_CODE_DESCEND     = "descend"
ACTION_CODE_YAW         = "yaw"
ACTION_CODE_HOVER       = "hover"
ACTION_CODE_RETURN_HOME = "return_home"

# ── 飞行状态 ──
FLIGHT_STATUS_IDLE      = "idle"
FLIGHT_STATUS_HOVERING  = "hovering"
FLIGHT_STATUS_PLANNED   = "planned"
FLIGHT_STATUS_EXECUTING = "executing"
FLIGHT_STATUS_COMPLETED = "completed"
FLIGHT_STATUS_ABORTED   = "aborted"

# ── 飞行模式 ──
MODE_MANUAL = "manual"  # forward_last_human_message 免审路径
MODE_AUTO   = "auto"    # propose_to_alpha 经人审核后执行

# ── alert 级别 ──
ALERT_LEVEL_WARNING = "warning"
ALERT_LEVEL_CRITICAL = "critical"

# ── reject 原因 ──
REJECT_UNKNOWN_ACTION_CODE     = "unknown_action_code"
REJECT_OUT_OF_BOUNDARY         = "out_of_boundary_after_clamp"
REJECT_EGO_PLANNER_UNREACHABLE = "ego_planner_unreachable"
