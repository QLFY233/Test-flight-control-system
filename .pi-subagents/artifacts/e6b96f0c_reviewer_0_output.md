# backend-A（Agent 中枢）全面代码审查报告

- 审查范围：backend-A 全部核心模块（main / lifecycle / state / config / agents / web / tools / speech / analytics / ipc / bus / db / monitor_trigger / tests）
- 审查依据：code-review-skill（Python + FastAPI 指南）、`docs/specs/`（A-B 接口冻结、总体架构）、`CLAUDE.md` 工作约定
- 运行环境确认：**backend-A 运行于 Python 3.10.19（.venv-A；start_all.sh 使用 pyenv 3.10.19）**，backend-B 才是 Python 3.8 侧。main.py 文档字符串、tests/test_all.py 头注、CLAUDE.md 均一致。因此"Python 3.8 兼容性"检查项对 backend-A 不适用：代码使用 `X | None`、`list[float]`、`asyncio.to_thread`（3.9+）、`time.time_ns`（3.7+），全部 3.10 安全；未发现 3.11+ 特性（无 match、无 asyncio.timeout、无 TaskGroup、无 dataclass slots）。
- 测试运行：`.venv-A/bin/python tests/test_all.py` → **47/47 通过**（含 msgpack 帧、AppState NaN 截断、总线路由、DB CRUD、TelemetryBuffer flush）。

---

## 🔴 blocking

### B1. α 指令下发失败被静默误报为"执行中"（错误状态机）
`agents/alpha.py:163-181` + `bus/router.py:24-31`
`bus_router.call()` 在 B 侧转发失败时**内部捕获异常并返回 `msg_type="error"` 字典**（`_error(call_id, to, str(exc))`，router.py:29-31），异常不会抛给 `_dispatch_action`。而 `_dispatch_action` 只检查 `payload.get("status") == "rejected"`，其余一律 `self._state.flight_status = FLIGHT_STATUS_EXECUTING`（alpha.py:178）。
后果：B 断开时，α 认为指令已下发、置为 executing；`_tick` 的 `elif current_action_plan...` 分支（alpha.py:132）又是 `pass`（计划未完成则不动作），因此**系统会卡在 "executing" 状态，永不回退 hover**。另外 IPC 是 fire-and-forget（`_send_and_wait` 返回 `{"status": "sent"}`，无 result 回包），`payload.get("status")=="rejected"` 分支实际是死代码——B 的 reject 走独立 event 通道。
修改建议：`_dispatch_action` 先校验 `result.get("msg_type") == "result"` 且 `payload.get("status") != "error"`，失败时 `logger.error` + `await self._send_hover()`；reject 判定应依赖 `_handle_reject`（bridge）驱动的状态回调，而不是调用返回。

### B2. WS broadcast 持锁 await + 与 IPC 收帧路径串行耦合 → 单客户端拖垮整条链路
`web/ws.py:28-41` + `bus/bridge.py:115-133`（`_handle_pose` → `_ws_pose` → `broadcast`）
`broadcast()` 在 `async with _connected_lock:` 内对每个客户端 `await ws.send_text(payload)`：锁跨 await 持有，任一客户端 TCP 背压（慢/断网）都会阻塞全部广播。且 `broadcast_pose` 由 IPC `_recv_loop` → `dispatch_b_event` → `_handle_pose` 同步 await 调用（10Hz）：一个慢 WS 客户端 → send_text 阻塞 → **IPC 收帧停摆** → B 侧发送缓冲区回压 → 心跳/姿态链路级联恶化。
修改建议：锁内只做 `_connected` 快照复制，锁外并发发送；或为每个客户端维护有界 asyncio.Queue + 独立发送 task，队列满即断开该客户端；同时把广播从 IPC 收帧路径解耦（入队后返回）。

---

## 🟡 important

### I1. α LLM 客户端跨事件循环复用（asyncio.run 每调用新建 loop）
`agents/alpha_llm.py:60` + `agents/llm.py:43-51`
`translate()` 每次调用 `asyncio.run(self._translate_async(...))`（每次新建并销毁事件循环），但 Agent 的 httpx `AsyncOpenAI` 客户端在 `make_agent()` 时创建一次并**在 agent 生命周期内复用**（已核对 pydantic-ai 2.0.0 `providers/openai.py`：`create_async_http_client()` 于构造时创建，注释明示"client 生命周期随 provider/agent 退出而结束"；`_set_http_client` 无运行期调用）。httpx 连接池绑定事件循环 → 同一进程内第二次翻译大概率报 "Event loop is closed" 类错误 → α 间歇性降级为 hover（有退避但功能受损，需重启恢复）。
修改建议：为 α 单独建一个常驻事件循环线程（`new_event_loop` + `run_forever`，主循环用 `run_coroutine_threadsafe` 提交）；或把 `translate` 改为 async 并在 app 循环直接 await（接受 1~5s 阻塞）；或每次调用重建 Agent。**建议上线前做两次连续 LLM 翻译的实证验证**（本环境无 API key，无法实测）。

### I2. 提议审批 TOCTOU 竞态 → 重复注入 α 队列
`web/routes.py:81-100`
`approve_proposal` 先读 `s.pending_proposal`、比对 id、再 `push_alpha_input`，全程无锁；两个并发 POST 可同时通过检查 → 同一意图被注入队列两次 → 无人机重复执行同一指令。
修改建议：在 `AppState` 上加 `pending_proposal` 的原子认领（如 `async with s._lock:` 内取出后立即置 None 再 push），或改用 `pending = s.pending_proposal; s.pending_proposal = None` 的"先置空后处理"顺序（不经 await 的间隙）。

### I3. TelemetryBuffer flush task 泄漏 + stop 用 sleep 猜测
`db/repos.py:147-157`
`start()` 的 `asyncio.create_task(self._flush_loop())` 不保存引用；`stop()` 用 `await asyncio.sleep(0.05)` 等待而非取消/等待任务 → 关停竞态、可能 "Task was destroyed but it is pending" 告警，stop 返回后 flush 仍可能运行。
修改建议：保存 `self._task`；`stop()` 中 `self._running=False` 后 `await self._task`（内部捕获 CancelledError），再清残留 buffer。

### I4. 遥测批量写入：单条 UNIQUE 冲突丢整批
`db/repos.py:179-191` + `db/models.py:69`
`insert(Telemetry), rows` 批量插入，`UniqueConstraint(session_id, t)` 一旦命中（同秒重复时间戳），IntegrityError 使**整批 1 秒遥测丢失**（仅错误日志）。
修改建议：SQLite 用 `insert(Telemetry).prefix_with("OR IGNORE")`，或插入前按 (session_id, t) 去重，或逐条捕获 IntegrityError。

### I5. IPC 断连路径不关闭 A 侧 writer（fd 泄漏）
`ipc/server.py:59-77`
`_handle_client` 的 `finally` 只清引用（`self._writer = None`），**从不 `writer.close()`**；帧超限路径（`_recv_loop` return，88-92 行）与正常断连都会泄漏 A 侧 socket/fd。B 每 ~1s 重连 → 持续泄漏。
修改建议：finally 中 `if self._writer: self._writer.close()`（可加 `await self._writer.wait_closed()`），帧超限路径显式关闭。

### I6. 生产入口 run_a.py 用 WARNING 级别日志，破坏可观测性 + start_all.sh 就绪检查失效
`run_a.py:7,10` + `start_all.sh`
`logging.basicConfig(level=WARNING)` 压制全部 INFO 日志（lifecycle 里程碑、α 翻译、β 创建）；`uvicorn.run(log_level='warning')` 同时压制 "Application startup complete." —— **已在本机实测验证**（info 级别可见、warning 级别为空）→ start_all.sh 的 `grep -q "Application startup complete"` 永远超时，显示"启动超时"误导。
修改建议：`log_level='info'` 且 basicConfig 用 INFO（main.py 的配置是正确的，run_a.py 与之对齐即可）；start_all.sh 改 grep 一个 A 侧自产就绪日志。

### I7. 生命周期/接线异常被吞，缺 fail-fast 与 traceback
`lifecycle.py:81-124`
`_start_alpha`/`_start_beta`/`_init_web_context` 全部 `except Exception: logger.warning(f"...: {e}")`——无 `exc_info`、不区分"缺 API key"（可降级）与"import/接线错误"（应失败）。`_init_web_context` 失败后 `_db_factory` 仍为 None，DB 路由全部 `NoneType not callable` → 500。
修改建议：非预期异常 `logger.exception(...)` 并在 startup 阶段 fail-fast（抛出让 uvicorn 启动失败）；确需降级的路径明确列出白名单异常并打 traceback。

### I8. 安全：全站无鉴权 + 绑定 0.0.0.0 + 可经 REST/WS 注入飞控指令
`web/routes.py:81-117`、`web/ws.py:111-160`、`main.py:78-80`、`run_a.py:10`
`POST /api/proposals/{id}/approve` 与 β 工具链（`forward_last_human_message` 免审直进 α 队列，tools/beta_tools.py:208-236）可被任意网络对端触发飞行动作；无鉴权、无限流、无输入长度上限（SSE `ChatRequest.message` 无限长，可致 LLM 成本放大）。对飞控系统是实质性风险。
修改建议（按风险顺序）：默认绑定 127.0.0.1；对变更类端点（approve/reject、chat、WS）加共享密钥头校验；`message`/`intent` 设长度上限。

---

## 🟢 nit

- **N1** `bus/bridge.py:115-148`：`_handle_pose` 在 IPC 收帧循环内串行做 state 更新 + WS 广播 + 遥测入缓冲；修复 B2 后建议进一步解耦（队列化）。
- **N2** `ipc/server.py:79-113`：正常断连（`IncompleteReadError`）被当作 warning 日志，B 每秒重连会刷屏；显式捕获 `asyncio.IncompleteReadError` 降为 debug/info。
- **N3** `ipc/frames.py`：`encode_frame/recv_frame` 与 server.py 内联的打包/长度前缀逻辑重复且 server 未复用——保留一个实现。
- **N4** `web/routes.py:146-156`：遥测接口 `rows[:1000]` 静默截断，无分页/limit 参数说明。
- **N5** `web/routes.py:77`：`list_sessions(limit: int = 10)` 无上限，`?limit=100000` 可拖垮 DB；用 `Query(le=100)`。
- **N6** `state.py:36-50`：`ActionPlan` dataclass 是死代码（alpha.py 用裸 dict 存 `current_action_plan`，仅测试使用）；二选一。
- **N7** `db/session.py:27-31`：`get_session()` 异步生成器依赖从未被使用（路由直接 `_db_factory()`），docstring 与实际不符。
- **N8** `agents/alpha.py:200-224`（`_log_action`）：函数内局部 import 且 `session_id` 用秒级 `strftime` 自动生成——同一秒内两条指令共享 session_id，会话数据混淆；且 `create_session()`（db/repos.py:38）**全仓无调用**，flight_sessions 行从不创建，SQLite 未开 `PRAGMA foreign_keys`（全仓无该 pragma）→ 孤儿 conversations/telemetry 行。建议：更细粒度 session id + 显式建 session 行。
- **N9** `monitor_trigger/trigger.py:18-33`：`handle_alert` 是死代码，bridge._handle_alert 与 lifecycle 均未接入；接入或删除。
- **N10** `speech/stt_client.py:22-27,100-130`：host 提取用 `replace("wss://","").replace("/v1","")` 脆若弦；`finish()` 接收循环无超时（服务端不返回 status=2 则永久挂起）。阶段 L 接线前必须加 timeout。
- **N11** `speech/tts_client.py:29-32`：`import time, hashlib` 未使用。
- **N12** `analytics/fft.py:44-50`：numpy 路径对 1 样本数据崩溃（`np.argmax(mag[1:])` 空数组）；DFT 路径 `half>=51` 时 frequencies 与 magnitudes 长度不一致；`n<2` 提前返回。
- **N13** `db/models.py:26-28`：FlightSession 用 naive `datetime.utcnow`，Environment/Conversation 用 aware `datetime.now(timezone.utc)`——SQLite 列内混存两种时区语义。
- **N14** `web/routes.py:13`：`import time` 未使用；`web/sse.py:7` 同。

---

## 💡 suggestion

- **S1** `main.py`：无 CORSMiddleware。生产同源（StaticFiles 挂 /）没问题，但 CLAUDE.md §4.3 的 dev 流程（:3456 http.server）中 frontend/js/api.js:6 硬编码 `http://localhost:8000` → 跨域请求会被浏览器拦截。加 `allow_origins` 白名单（localhost dev）或文档明确"仅同源访问"。
- **S2** `web/ws.py:111-160`：`json.loads(raw)` 无防御——单条畸形消息即断开该客户端；无单消息大小上限。改为解析失败回 error 帧，并限长。
- **S3** `agents/alpha.py:124-137,152-160`：一次失败会触发两次 `_send_hover`（_translate 内一次、_loop except 内一次）；去重。
- **S4** `state.py:107-109`：`current_pose` 直接返回活对象且不带锁（`update_pose` 的 quat extend 为原地修改）；10Hz 频率下返回浅拷贝成本可忽略，避免跨协程读到半更新态。
- **S5** `config_loader.py:8-16`：库函数内 `print`+`sys.exit(1)`；改抛带路径信息的异常由 main 决定退出。

---

## 🎉 praise

- **协议单一事实源**：`shared/protocol.py` 由 A/B 两侧 symlink 引用，已 diff 验证逐字一致，符合接口冻结 spec 的变更控制要求。
- **安全默认姿态**：`update_pose` 的 NaN/Inf 截断、α 动作编码白名单校验、LLM 失败→hover+指数退避、IPC 16MiB 帧上限 + 首 pong 版本协商 + 5s pong watchdog，都是扎实的防御性设计。
- **异步边界处理**：α 用 `asyncio.to_thread` 隔离 LLM 阻塞调用（设计正确，问题仅在 I1 的 loop 复用细节）；alpha loop task 保存引用并正确 cancel。
- **TelemetryBuffer 批量落库**（锁+批量+ORM insert）与整体分层（db/ipc/bus/web/agents）清晰，模块职责单一。
- **测试质量**：47 项检查覆盖协议一致性、帧编解码、NaN 处理、总线路由、DB CRUD、缓冲 flush，全绿；且测试自清理临时 DB。

---

## 总体结论：🔄 Request Changes

两个 🔴（B1 状态机误报、B2 广播持锁耦合 IPC）都是可复现、可定位、修改面小的逻辑问题，直接影响飞行指令链路可信度；建议修复后合入。🟡 中 I1（LLM 跨 loop 复用）需一次双连发实证验证后处理，I8（无鉴权）至少先降级到绑定回环地址。

### 前 5 大问题
1. **B1** alpha.py:163-181 — B 断开时下发失败被静默置为 executing，系统卡死不回退 hover（逻辑错误+安全姿态错误）。
2. **B2** web/ws.py:28-41 + bridge.py:130-133 — 广播持锁 await 且与 IPC 收帧串行，单慢客户端可拖垮姿态/心跳链路。
3. **I1** alpha_llm.py:60 — `asyncio.run` 每调用新建 loop 复用 loop-affine 的 httpx 客户端，二次翻译高风险失败。
4. **I2** routes.py:81-100 — 提议审批 TOCTOU，并发重复注入飞控指令。
5. **I6** run_a.py:7-10 — WARNING 日志压制全部 INFO + start_all.sh 就绪检查必超时（已实测）。

### 残余风险（residual risks）
- I1 依据 pydantic-ai 2.0.0 源码推断（客户端生命周期注释 + `_set_http_client` 无运行期调用），本环境无 DeepSeek API key 未做双连发实测，需一次实证验证。
- B1/B2 经代码路径分析确认，未做含 B 侧+仿真器的端到端运行复现。
- SSE/β 流式、STT/TTS（讯飞）均未在本环境实测（无凭据）。