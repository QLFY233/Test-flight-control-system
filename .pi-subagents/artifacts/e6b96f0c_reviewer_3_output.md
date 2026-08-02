# A/B 跨进程协议与接口一致性审查报告（契约审查）

审查范围：backend-A ↔ backend-B（Unix socket + msgpack）、backend-A ↔ 前端（REST/SSE/WS）、以及 `docs/specs/总体/2026-07-05-A-B-接口冻结.md`（权威基准，schema_version=2）。

审查基准日：git HEAD `49158ef`。两侧测试套件均通过（A 47/47，B 58/58）。

---

## 0. 总体结论

**A↔B 跨进程 IPC 核心契约高度一致且防漂移设计优秀**：两侧 `bus/protocol.py` 是同一文件 `shared/protocol.py` 的软链接（物理上不可能漂移），帧编解码 `ipc/frames.py` 逐字节相同，心跳/版本协商/帧上限/重连策略全部对称，B 侧上行 `to`/payload 字段与冻结文档对齐度高。✅ 无 A↔B 互不兼容的阻断项。

**问题集中在 A→前端（WS）与 前端→A（REST）契约**：存在 3 个 🔴 阻断项（WS 载荷结构不匹配导致全部实时数据被前端丢弃、`/api/field` vs `/api/field/config` 404、abort 路由缺失）、以及若干 🟡 文档偏离与断链（status/alpha_output WS 从不广播、reject 不注入 α、telemetry payload 偏离等）。

---

## 1. 🔴 blocking

### 🔴-1 WS 下行消息载荷结构不匹配 → 全部实时数据被前端丢弃
`backend-A/web/ws.py:44-113` ↔ `frontend/js/ws.js:150-166`（`_dispatch`）
- 后端广播为**顶层字段**：`{"type":"pose","schema_version":2,"pos":[...],"quat":[...],...}`（ws.py `broadcast_pose/alert/status/alpha_output/reject/link_status` 全部如此，与前端 spec §3.3 `PoseMessage` 等接口定义一致）。
- 前端 `WsManager._dispatch` 调用 `handler(data.payload, data)` —— 后端消息**没有 `payload` 键**，`data.payload === undefined`。
- 后果（`frontend/js/app.js:177-209`）：`pose/status/alert/reject/alpha_output/link_status` 全部 handler 首行 `if (!p) return;` 短路，实时数据 100% 丢失；`alert`/`reject` handler 直接 `bus.emit(..., undefined)`。仅内部构造的 `{type:'connection',payload:{...}}`（ws.js:41,77）带 payload，连接状态正常。
- 修复：`ws.js:_dispatch` 改为 `handler(data.payload !== undefined ? data.payload : data, data)`；或将后端统一改为 `{type, payload:{...}}` 包装。建议前者（后端与 spec 已对齐）。

### 🔴-2 前端 `getFieldConfig` 调 `/api/field`，后端只提供 `/api/field/config`
`frontend/js/api.js:150-152` ↔ `backend-A/web/routes.py:43-46`（`@router.get("/field/config")`）
- 前端 `api.js:152`：`return this.get('/api/field');`；实际调用点在 `frontend/js/app.js:154`（启动即调）。
- 后端无 `/api/field` 路由 → 404 → `.catch(() => store.set('field.obstacles', []))` 静默吞掉 → 场地边界/家点配置永远加载不到（前端 spec 行 1527 明确要求 `GET /api/field/config`）。
- 修复：`api.js:152` 改为 `'/api/field/config'`。

### 🔴-3 `POST /api/sessions/{id}/abort` 路由缺失（spec 要求、前端调用、后端 404）
`frontend/js/api.js:130-132`（`abortSession`）↔ `backend-A/web/routes.py`（无此路由）↔ 前端 spec 行 562 `POST /api/sessions/{id}/abort → 中止`
- 后端 `routes.py` 只有 `GET /api/sessions`（list_sessions）。`BottomBar.js:53` 的 ABORT 按钮调用 `apiManager.abortSession(sessionId)` → 404 → "中断失败"。
- 叠加 🔴-1 与 🟡-1（status 不广播、枚举错位），ABORT 按钮在 "executing" 状态下根本不显示，应急中断路径全链路失效。
- 修复：后端补 `POST /api/sessions/{id}/abort` 路由（或按现行设计改为经 IPC 下发 `call.abort` + 前端适配）。

### 🔴-4 B→A `event.status` → A 不转发 WS `status`（冻结契约中段断链）
`backend-A/bus/bridge.py:87-90`（`_handle_status`）↔ `backend-A/web/ws.py:70-80`（`broadcast_status`）
- 冻结文档 §5：status 事件 → 更新 `flight_status` + **转发前端 WS `status`**（含当前动作/总动作进度）。
- 实现：`_handle_status` 只更新 state + 打日志，**从不调用 `_ws_status`**；`broadcast_status` 全仓无任何调用点（grep 证实仅定义与注入）。→ 前端永远收不到任务进度。
- 修复：`_handle_status` 中补 `await _ws_status(flight_status, mode, currentAction, totalActions)`（或由 α loop 定期广播）。

---

## 2. 🟡 important

### 🟡-1 前端 flight.status 枚举与后端/冻结文档不一致（'running'/'paused' vs 'executing'）
`frontend/js/state.js:118`（`status: 'idle' | 'running' | 'paused' | ...`）↔ `shared/protocol.py` `FLIGHT_STATUS_EXECUTING='executing'`、冻结文档 §5 status `flightStatus`
- `BottomBar.js:47` `showAbort = status === 'running' || status === 'paused'` —— 后端推 `'executing'`，永不匹配 → 中断按钮永不显示（叠加 🔴-3）。
- 修复：前端状态树与判断改用冻结枚举 `idle/hovering/planned/executing/completed/aborted`。

### 🟡-2 WS `link_status` 字段 shape：前端 `backend_a/backend_b/drone/llm` vs 后端+spec `link/state`
`frontend/js/app.js:209` ↔ `backend-A/web/ws.py:107-113`、`ipc/server.py:166-172`、`agents/alpha.py:199-203`
- 后端与 spec（前端 §3.3 `LinkStatusMessage`）一致：`{link:'A-B'|'llm', state:'up'/'down'/'ok'/'error', detail}`；前端 handler 却读 `p.backend_a`/`p.backend_b`/`p.drone`/`p.llm` —— 即使修好 🔴-1 也取不到值。
- 附带：后端 state 取值 `'up'/'down'/'ok'/'error'` 偏离 spec 枚举 `'ok'|'degraded'|'down'`（🟢）。
- 修复：前端 handler 改为按 `link`+`state` 映射 `connection.backendA/backendB/drone/llm`。

### 🟡-3 `alpha_output` WS 消息从不广播（spec：α loop 产出 → 前端展示动作+目标点）
`backend-A/web/ws.py:83-93`（`broadcast_alpha_output` 定义）↔ `backend-A/agents/alpha.py`（无调用）↔ 冻结文档 §5 注、前端 §3.3 `AlphaOutputMessage`
- 全仓无调用点。α 翻译下发的 ActionCommand/目标点前端（α 界面）看不到。
- 修复：α loop `_dispatch_action` 成功后调 `broadcast_alpha_output(action_cmd, goal, remaining)`。

### 🟡-4 A 侧 `dispatch_b_event` 不校验 `to` 字段（spec：未知 `to` 记日志丢弃）
`backend-A/bus/bridge.py:47-58` ↔ 冻结文档 §3（"其余 5 类必须 `to` 组件名精确命中，否则视为协议错误记日志丢弃"）、开放式接口规范 §3 规则
- 实现按 `tool` 分发，完全忽略 `to`。当前 B 侧全部上行 `to` 正确（pose/telemetry/status/reject→alpha、alert→beta、pong→heartbeat），暂无实际危害，但违反契约防御要求。
- 修复：`dispatch_b_event` 开头校验 `to`，未命中记日志丢弃。

### 🟡-5 `reject` reason 枚举偏离冻结值
`backend-B/small_model/component.py:199`（`f"unknown_action_code:{code}"`）↔ `shared/protocol.py` `REJECT_UNKNOWN_ACTION_CODE='unknown_action_code'`、冻结文档 §5
- 冻结 reason 取值：`unknown_action_code` / `out_of_boundary_after_clamp` / `ego_planner_unreachable`。B 侧未知编码时发 `"unknown_action_code:takeoff"`（拼了具体编码），`REJECT_UNKNOWN_ACTION_CODE` 常量从未被使用（stub.py:129 同）。`out_of_boundary_after_clamp` 与常量一致 ✅。
- 影响：A 仅透传 WS reject，前端仅展示 —— 语义仍可读，但"冻结枚举"被破坏。修复：`_send_reject` 用常量（可在 detail 里附编码）。

### 🟡-6 reject 事件未注入 α 上下文（spec：注入 α 上下文 → 下轮重想或兜底 hover）
`backend-A/bus/bridge.py:93-104`（`_handle_reject`）↔ 冻结文档 §3/§5
- `_alpha_loop_ref` 已注入但 `_handle_reject` 从未使用；注释"α 下轮 tick 会发送 hover"不成立 —— α loop `_tick` 在 `current_action_plan` 非空时直接 `pass`，A 侧 `current_action_plan` 未被 reject 清空 → 无重想也无 hover。安全默认缺失。
- 修复：reject 时清空/标记 A 侧 `current_action_plan` 并注入 α 队列或直接下发 `call.hover`。

### 🟡-7 `telemetry` payload 字段偏离冻结文档
`backend-B/lifecycle.py:248-262`、`backend-B/run_b.py:66-68` ↔ 冻结文档 §5（`{vel, accel, imu, ts}`）
- 实现发送 `{accel, angularVel, ts}`（缺 `vel`/`imu`，多 `angularVel`）。A 侧 `_handle_telemetry` 先导仅日志（bridge.py:85-86），暂无害，但 §5 分帧约定（pose+telemetry 合并入历史库 quat/accel/angular_velocity 字段）后续实现时会踩坑。
- 修复：按冻结 payload 补 `vel`/`imu` 字段。

### 🟡-8 心跳 ping 实现为 `event`+`ping`，冻结文档写 `call.ping`
`backend-A/ipc/server.py:136-150` ↔ 冻结文档 §6（"A 每 2s 发 `call.ping`"）
- 实现：`msg_type=MSG_TYPE_EVENT, tool='ping'`。B 侧 `dispatch.handle_incoming` 同时容忍 `EVENT+ping` 与 `CALL+ping`（dispatch.py:30-36,52-54），**两侧互操作无问题**，属文档-代码偏离。建议：改实现为 `call`（或改文档措辞），并顺手让 A 侧 pong 校验 `to=='heartbeat'`（冻结文档 §3 要求，现未校验，🟢）。

### 🟡-9 REST 会话端点与前端 spec 偏离
`backend-A/web/routes.py` ↔ 前端 spec 行 559-563
- spec：`POST/GET/PATCH /api/sessions/{id}`、`GET /api/history/sessions?limit&offset&status&search`；实现：仅 `GET /api/sessions`（list）。前端 `api.js` 的 `createSession`（POST /api/sessions）为死代码但指向不存在的路由。`GET /api/sessions` 前后端一致可用 ✅（HistoryPage/OverviewPage 在用），属 spec 路径命名偏离。
- 修复：按 spec 补齐 POST/PATCH/abort 会话端点（abort 已在 🔴-3）。

---

## 3. 🟢 nit

- **`getTelemetry`/`getConversations`/`getCurrentPose` 死代码且路径错误**（`frontend/js/api.js:100-108,120-123`）：`/api/telemetry`、`/api/conversations?session_id=`、`/api/pose` 均与后端实际路由（`/api/history/telemetry/{sid}`、`/api/history/conversations/{sid}`、`/api/current-pose`）不符；无调用点，一旦启用即 404。建议按后端路由修正或删除。
- **`/api/history/telemetry` 查询参数**：实现 `t_start`/`t_end`（routes.py:107）vs spec `t_from`/`t_to` —— 参数命名偏离。
- **`getProposals(sessionId)`** 传 `session_id` 查询参，后端忽略额外参数（FastAPI 宽容），可用；建议去掉。
- **A→B `action` call args 包装**：实现 `args={"action": ActionCommand}`（alpha.py:127、bridge.py:31-38），冻结文档 §4 写 `args=ActionCommand`；两侧一致，仅文档措辞偏离。且 §2 "`action` call 携 ActionCommand+pose+env" —— 实现只带 action（B 侧 small_model 自取 BState 位姿，行为可接受）。
- **`sync_response` 消息 shape 偏离 spec**：ws.py:131-143 发 `{current_pose:{pos,quat,vel}, flight_status, ipc_connected, pending_proposal}` vs spec `{pose, quat, status}`；且前端从不发 `sync`、无 `sync_response` handler —— 死路径。
- **SSE 文档字符串声称发 `tool_call_start`/`tool_call_result`**（sse.py:2,33-35）但实现从不发（仅 `plan`/`text`/`error`）；前端 sse.js 解析超集，无影响。
- **ws.py 各 broadcast 硬编码 `"schema_version": 2`**：建议从 `shared/protocol.py` 导入 `SCHEMA_VERSION`，避免下次升版漏改。
- **B 侧 dispatch `_handle_call` 读取 `to` 但路由硬编码 small_model**（dispatch.py:46,61）：冻结枚举下无碍，建议删除未用变量。
- **B 侧断连未显式触发 small_model 切 hover**（`ipc/client.py:76-95`）：靠 GoalPublisher 持续发最后 setpoint（等效悬停于最后目标），与 §6 "断连 → small_model 切 hover" 措辞有差异，风险可接受，建议显式调用 `_handle_hover`。
- **前端 `link_status` 状态值**：后端 `'up'/'down'/'ok'/'error'` vs spec 前端 §3.3 `'ok'|'degraded'|'down'`。

---

## 4. 一致性检查表

### A↔B IPC 消息（冻结文档 §2-§6）

| 消息/常量 | 状态 | 说明 |
|---|---|---|
| `schema_version` (=2) | ✅ 一致 | 两侧软链同一 `shared/protocol.py`；文档 §9 = 2 |
| `MSG_TYPE_CALL/RESULT/EVENT/ERROR` | ✅ 一致 | 同源文件 |
| `call.action`（A→B） | ✅ 一致 | 两侧 `args={"action": ActionCommand}` 同构；⚠️ 与文档 §4 措辞偏离（🟢） |
| `call.abort`（A→B） | ✅ 一致 | args={}，B 映射 small_model.abort |
| `call.hover`（A→B） | ✅ 一致 | args={}，B 映射 small_model.hover |
| `ping`（A→B） | ⚠️ 存疑 | 实现为 `event`+`ping`，文档写 `call.ping`（🟡-8）；B 两侧都容忍，互操作 OK |
| `event.pong`（B→A） | ✅ 一致 | `to='heartbeat'`、带 schema_version 供 A 版本校验；A 未校验 `to`（🟢） |
| `event.pose`（B→A） | ✅ 一致 | payload `{pos,quat[w,x,y,z],vel,accel,angularVel,ts}` 与 §3/§5 逐字段一致；10Hz；to=alpha |
| `event.telemetry`（B→A） | ⚠️ 存疑 | payload `{accel,angularVel,ts}` vs 文档 `{vel,accel,imu,ts}`（🟡-7）；A 仅日志 |
| `event.status`（B→A） | ✅ 一致 | payload `{flightStatus,mode,currentAction,totalActions,taskId}` 与 §5 一致；但 A 不转发 WS（🔴-4） |
| `event.reject`（B→A） | ⚠️ 存疑 | reason 枚举 `unknown_action_code:<code>` 偏离冻结值（🟡-5）；A 不注入 α（🟡-6） |
| `event.alert`（B→A） | ✅ 一致 | `{level,code,detail,suggestion,ts,action_index}`、to=beta、suggestion 置空、节流 2s/critical 不节流，全部对齐 §5 |
| 动作编码表（9 个） | ✅ 一致 | shared 源 + B `action_codes.py` + A `alpha_llm.py` 校验集合三方一致 |
| 飞行状态枚举（6 个） | ✅ 一致（A/B） | shared 源；❌ 前端 state.js 用 running/paused（🟡-1） |
| alert 级别 / MODE / reject 常量 | ✅ 一致 | shared 源 |
| 帧格式（4B 大端 + msgpack） | ✅ 一致 | 两侧 `frames.py` 逐字节相同；16MiB 上限、use_bin_type=True、raw=False |
| 心跳周期/超时/重连 | ✅ 一致 | 2s ping / 5s pong 超时 / 1s 恒定重连，与 §6 对齐 |
| socket 路径 / A server / B client | ✅ 一致 | `/tmp/flight_control_AB.sock`；A unlink、B 重连 |

### backend-A ↔ 前端（REST/SSE/WS）

| 端点/消息 | 状态 | 说明 |
|---|---|---|
| `POST /api/chat/beta`（SSE） | ✅ 一致 | 事件名 text/tool_call_start/tool_call_result/plan/error 前端超集解析；`plan` 事件含 id/proposalId/intent/actions 与 FlightPlanCard 对齐 |
| `GET /api/overview` | ✅ 一致 | `{flight_status,ipc_connected,session_id,last_llm_ok,recent_sessions}`，OverviewPage 仅用 sessions 子集 |
| `GET /api/sessions` | ✅ 一致 | 前后端一致；⚠️ spec 命名 `/api/history/sessions`（🟡-9） |
| `POST /api/sessions` / `{id}` PATCH / `{id}/abort` | ❌ 不一致 | 后端缺失（🔴-3）；前端 createSession/abortSession 指向空路由 |
| `GET /api/proposals` + `POST {id}/approve|reject` | ✅ 一致 | 单一路径 C3；approve 校验 pending.id == proposal_id ✅ |
| `GET /api/field/config` | ❌ 不一致 | 前端调 `/api/field`（🔴-2） |
| `GET /api/current-pose` | ⚠️ 存疑 | 前端 `getCurrentPose` 调 `/api/pose`（死代码，🟢） |
| `GET /api/history/telemetry/{sid}` | ⚠️ 存疑 | 前端调 `/api/telemetry`（死代码）；参数名 t_start/t_end vs t_from/t_to（🟢） |
| `GET /api/history/conversations/{sid}` | ⚠️ 存疑 | 前端调 `/api/conversations`（死代码） |
| `GET/POST /api/environments` | ✅ 一致 | |
| `GET /api/health`、`/api/link-status` | ✅ 一致 | 前端未用，无冲突 |
| WS `pose` 下行 | ❌ 不一致 | 后端/spec 顶层字段，前端 handler 收 `data.payload=undefined`（🔴-1）；且前端字段名 `position/velocity/attitude` 与后端 `pos/vel/quat` 不符 |
| WS `status` 下行 | ❌ 不一致 | 🔴-1 + 🔴-4（后端从不发）+ 字段 camel/snake 错位 + 状态枚举错位（🟡-1） |
| WS `alert` / `reject` 下行 | ❌ 不一致 | 🔴-1 丢弃；字段名本身对齐（level/code/detail/...、reason/actionIndex/...） |
| WS `alpha_output` 下行 | ❌ 不一致 | 🔴-1 + 后端从不广播（🟡-3）；前端字段名 `planned/action_sequence/current_target` 与后端 `action/goal/remaining_actions` 不符 |
| WS `link_status` 下行 | ❌ 不一致 | 🔴-1 + 前端字段 `backend_a/...` 与后端 `link/state` 不符（🟡-2） |
| WS 上行 `sync` / `voice_frame` / `tts_request` | ✅ 一致 | 后端处理三者（sync 有响应、voice_frame/tts_request 先导忽略）；前端只实际发 voice_frame ✅；sync 前端从不发（死路径） |
| WS 上行 `approve_plan`/`modify_plan`/`reject_plan` | ⚠️ 存疑 | 前端 BetaPage 无 proposalId 时的 fallback，后端 ws_endpoint 不处理（仅 debug 日志），静默 no-op |

---

## 5. 已确认一致的良好实践（praise）

- `bus/protocol.py` 双侧软链单一 `shared/protocol.py` —— 从根本上杜绝枚举漂移，变更控制 §9 可落地。
- `ipc/frames.py` 两侧逐字节一致，msgpack `use_bin_type=True`/`raw=False` 跨 0.6/1.x 硬契约严格执行，且有 S0 测试覆盖（B test_all Test2）。
- 版本协商在首次 pong 时校验（server.py:108-115），版本不符即断连 —— 符合"不静默改"原则。
- B 侧上行 payload 冻结字段（pose/status/alert）与文档 §5 高度一致；`[w,x,y,z]` 四元数顺序全链路正确（run_b.py:55 → bridge → ws）。
- 测试套件覆盖协议常量/帧编解码/帧过大/注册表/路由错误路径（A 47 项、B 58 项全过）。

---

## 6. 修复优先级建议

1. 🔴-1 WS payload 结构（一行修复，恢复全部实时数据通道）
2. 🔴-2 `/api/field` → `/api/field/config`（一行修复）
3. 🔴-3 abort 路由补齐（后端补路由 + 前端枚举对齐后按钮才会显示）
4. 🔴-4 `_handle_status` 补 WS 转发（配合 🔴-1 生效）
5. 🟡-1 前端飞行状态枚举对齐冻结值
6. 🟡-2 link_status 前端字段对齐 `link`/`state`