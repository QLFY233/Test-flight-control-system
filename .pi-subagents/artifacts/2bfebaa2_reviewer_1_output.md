# Frontend 并行修复独立验证报告（verify-frontend）

- 验证方式：fresh context，只读验证（未修改任何代码），独立行为测试（`/tmp/code-review/verify-frontend-test.mjs`，不依赖修复者自测）
- 验证对象：`/home/QLFY233/Test-flight-control-system/frontend/**`（git HEAD `49158ef` + 工作区未提交修改）
- 参照：frontend-report.md（审查发现）、contract-report.md（契约发现）、fix-frontend.md（修复声明）
- 注：项目根无 `plan.md`/`progress.md`（frontend-report 亦确认）；进度文件在 `.pi-subagents/artifacts/progress/2bfebaa2/progress.md`

---

## 一、逐项验证结果表

### 必做 1：语法检查

| 项 | 结果 | 证据 |
|---|---|---|
| `node --check` 全部 `frontend/js/**/*.js` + sw.js | ✅ PASS | 40 个 js + sw.js 全部通过（`find js -name "*.js"` + sw.js 循环 node --check，0 失败） |
| `python3 -m py_compile frontend/serve.py` | ✅ PASS | 编译通过，无语法错误 |

### 必做 2：契约对齐复检

| 项 | 结果 | 证据 |
|---|---|---|
| ws.js `_dispatch` 兼容顶层消息 | ✅ PASS | `ws.js:172` `const payload = data.payload !== undefined ? data.payload : data;`；行为测试：后端顶层 `{type:'pose',pos:[1,2,3],quat:[...]}` → type handler 与 wildcard handler 均收到顶层对象；内部 `{type:'connection',payload}` 收到 payload |
| pose handler 字段 | ❌ **FAIL**（见遗留 1） | `app.js:210-218` 读 `p.pos`/`p.vel`/`p.attitude`；后端 `ws.py:56-66` broadcast_pose 广播 `pos`/`quat`/`vel`/`accel`/`angularVel`/`ts` —— **`quat` 未被读取**，`p.attitude` 字段后端不存在 → `drone.attitude` 恒为初始值永不更新 |
| status handler 字段 | ✅ PASS | `app.js:220-228` 读 `p.mode`/`p.flightStatus`/`p.currentAction`/`p.totalActions` ↔ `ws.py:70-80` broadcast_status 广播 `flightStatus`/`mode`/`currentAction`/`totalActions` 逐一命中（`p.progress` 为额外容错，后端无此字段但无害） |
| alert handler 字段 | ✅ PASS | `app.js:229` 透传 ↔ `ws.py:61-68` 广播 `level`/`code`/`detail`/`suggestion`/`ts`；ChatPanel 消费 `payload.level` ✅（`payload.message` 后端无 → JSON.stringify 兜底展示，见遗留 3） |
| reject handler 字段 | ✅ PASS（链路未闭合，见遗留 2） | `app.js:230` 透传 ↔ `ws.py:95-105` 广播 `reason`/`actionIndex`/`suggestedAction`/`ts`；字段名一致，但 `proposal-rejected` 事件全仓无消费者 |
| link_status handler 字段 | ✅ PASS | `app.js:244-253` 读 `p.link`/`p.state` ↔ `ws.py:107-113` 广播 `link`/`state`/`detail`/`ts`；`link==='A-B'`→backendA/backendB、`link==='llm'`→llm，与后端实际广播值（ipc/server.py `"A-B"`、alpha.py `"llm"`）一致 |
| alpha_output handler 字段 | ✅ PASS | `app.js:232-242` 读 `p.action.code`/`p.action.params`/`p.goal`/`p.remaining_actions` ↔ `ws.py:83-93` 广播 `action`/`goal`/`remaining_actions` 逐一命中（`p.planned` 为额外容错） |
| api.js 请求路径 vs routes.py | ✅ PASS（全项） | 见下方「REST 端点对照表」 |
| flight.status 枚举对齐 | ✅ PASS | `state.js:186` 注释冻结枚举 `'idle' | 'hovering' | 'planned' | 'executing' | 'completed' | 'aborted'`，初始值 `'idle'`；`BottomBar.js:47` `showAbort = status === 'executing'`；全仓无 `'running'`/`'paused'` 飞行状态残留（`paused` 仅存于 playbackState 回放注释，合法） |

### REST 端点对照表（api.js ↔ backend-A/web/routes.py）

| api.js 方法 | 请求路径 | routes.py 路由 | 结果 |
|---|---|---|---|
| getFieldConfig | `GET /api/field/config` | `@router.get("/field/config")`（prefix /api） | ✅ |
| abortSession | `POST /api/sessions/{id}/abort` | `@router.post("/sessions/{session_id}/abort")` | ✅（后端并行修复已补，含 IPC call.abort） |
| getTelemetry | `GET /api/history/telemetry/{sid}` | `@router.get("/history/telemetry/{session_id}")`（参数 t_from/t_end 已对齐 spec） | ✅ |
| getConversations | `GET /api/history/conversations/{sid}` | `@router.get("/history/conversations/{session_id}")` | ✅ |
| getCurrentPose | `GET /api/current-pose` | `@router.get("/current-pose")` | ✅ |
| getOverview | `GET /api/overview` | `@router.get("/overview")` | ✅ |
| getSessions | `GET /api/sessions` | `@router.get("/sessions")` | ✅ |
| createSession | `POST /api/sessions` | `@router.post("/sessions")` | ✅ |
| getEnvironments / saveEnvironment | `GET/POST /api/environments` | `@router.get|post("/environments")` | ✅ |
| getProposals | `GET /api/proposals`（已去 session_id 参数） | `@router.get("/proposals")` | ✅ |
| approveProposal / rejectProposal | `POST /api/proposals/{id}/approve|reject` | `@router.post("/proposals/{proposal_id}/approve|reject")` | ✅ |
| —（前端未调用） | — | `GET /api/health`、`GET /api/link-status` | ✅ 前端无调用，无冲突 |
| SSE chat | `POST /api/chat/beta`（ChatPanel 用 config.backend.sse_beta） | `backend-A/web/sse.py:36 @router.post("/beta")`（prefix /api/chat） | ✅ |

### 必做 3：XSS 修复抽查

grep `innerHTML` 全 frontend/js（约 55 处），逐点核对数据插值均经 `esc`/`escAttr`（escape.js）：

| 抽查点 | 结果 | 证据 |
|---|---|---|
| ChatMessage | ✅ PASS | `ChatMessage.js:30,42` toolName/toolArgs/tool_result 均 `esc(...)`；`_simpleMarkdown` 先 `esc(text)`（L58）再渲染管道；无 lookbehind 正则（L103 `/\*([^*\n]+)\*/g`） |
| SessionCard | ✅ PASS | `SessionCard.js:44` `title="${escAttr(...)}"`（引号已转义 `&quot;`/`&#39;`）；badge class 与文本均 esc/escAttr |
| AlphaPage | ✅ PASS | `AlphaPage.js:63` `esc(env.location)`、L73 `esc(flight.taskTitle)`、L80 `esc(JSON.stringify(flight.currentActionParams))`、L82 `esc(flight.mode/status)`、action 列表 `esc(a.code)`/`esc(target 数值)` 全覆盖 |
| BetaPage | ✅ PASS | `BetaPage.js:44` `esc(env.location)`、L119/127 `esc(e.message)` 错误信息 |
| HistoryPage | ✅ PASS | `HistoryPage.js:187-190` `esc(session.task_title)`/`esc(dateStr)`/`esc(session.status)`/`esc(session.task_summary)` |
| OverviewPage | ✅ PASS | `OverviewPage.js:197` `esc(e.message)`；indicator 用 `esc(i.label)`/`esc(getStatusText(...))`；env 数值插值（数字类型） |
| DashboardPanel | ✅ PASS | `DashboardPanel.js:42-44` title/window `esc`；L124-125 value/unit `esc`；`dp-body-${escAttr(panelId)}` 属性转义 |
| DashboardGrid | ✅ PASS | `DashboardGrid.js:64-68` `data-panel-id="${escAttr(id)}"`、`id="dash-panel-${escAttr(id)}"` |
| FlightPlanCard | ✅ PASS | `FlightPlanCard.js:85` `${esc(value + ' ' + units)}`（原遗漏点已修）；code/comment/title/intent/summary 全 `_esc` |
| StatusBar / FloatingBall / BottomBar | ✅ PASS | `StatusBar.js:44` `esc(flight.mode)`；`FloatingBall.js:88` `esc(item.icon)`；`BottomBar.js:31` `esc(actionLabel)` |
| escape.js 接入 | ✅ PASS | 12 个文件 import escape.js；残留检查：`_escapeHtml`/`FlightPlanCard_esc`/`streamingMessageEl`/`_resetHideTimer`/`_timeUnsub`/`_playbackUnsub` 仅注释提及，代码无残留 |

行为测试：`esc('<img onerror=...>')` → `&lt;img...&gt;` ✅；`escAttr('a" onmouseover="alert(1)')` → 引号转义不可逃逸 ✅；`escAttr("it's")` → `it&#39;s` ✅。

### 必做 4：关键修复真实性

| 修复项 | 结果 | 证据 |
|---|---|---|
| router.js pendingHash 递归 | ✅ PASS | `router.js:113-119` finally 中 `finalHash !== this.currentHash` 时递归 `_onChange()`；行为测试：factory 挂起期间 hash 变化 → 收敛到最终 hash，稳定后不重复导航 |
| HistoryChart 具名回调 off | ✅ PASS | `HistoryChart.js:41-45` `this._onSeek = (t) => this._updateTimeCursor(t); bus.on('playback-seek', this._onSeek)`；unmount（L50）`bus.off('playback-seek', this._onSeek)`（bus.on 确不返回 unsubscribe，event-bus.js:17-24 无 return，修复必要性成立）；原空 `playback-state-changed` handler 已删 |
| ChatPanel 闭包流状态 | ✅ PASS | `ChatPanel.js:107-111` `streamEl`/`bubble`/`streamContent`/`errored` 全部收敛到 `_sendMessage` 局部闭包；onComplete/onError 只操作自己的 streamEl；`errored` 双保险短路 |
| sse.js errored 标记 | ✅ PASS | `sse.js:43` `let errored = false`；L79 error 事件置位；L91 `if (!errored) onComplete(fullText)`；行为测试：error 事件后 onComplete 0 次、onError 1 次 |
| VideoPanel ro.disconnect | ✅ PASS | `VideoPanel.js:70-74` unmount `this._ro.disconnect()`；`img.onerror`（L49-57）坏帧回退无信号占位 |
| sw.js 版本化缓存名 | ✅ PASS | `sw.js:8` `CACHE_NAME = 'flight-control-v1-' + BUILD_ID`（BUILD_ID='2026-08-02'）；Stale-While-Revalidate（L44-61）；activate 清理旧缓存（L28-34）；escape.js 已入 STATIC_ASSETS（L23） |

### 必做 5：修复声明与代码一致性抽查（fix-frontend.md 逐项）

| 声明项 | 状态 | 代码证据 |
|---|---|---|
| 🔴-1 ws `_dispatch` payload 兼容 | ✅ done 属实 | ws.js:172 + 行为测试 PASS |
| 🔴-2 getFieldConfig → /api/field/config | ✅ done 属实 | api.js:152（`/api/field/config` 唯一调用点） |
| 🔴-3(前端) 枚举对齐 + showAbort | ✅ done 属实 | BottomBar.js:47 `status === 'executing'`；state.js 冻结枚举注释 |
| 🟡1 router 竞态 | ✅ done 属实 | router.js:113-119 |
| 🟡2 StatusBar rAF 节流 + 实例复用 | ✅ done 属实 | app.js:127-146（sb/bb 实例 + sbRaf/bbRaf + 4 订阅） |
| 🟡3 HistoryChart 泄漏 | ✅ done 属实 | HistoryChart.js:41-45,50 |
| 🟡4 SSE error 重复渲染 | ✅ done 属实 | sse.js:43,79,91 + ChatPanel.js:126,158 双保险 |
| 🟡5 ChatPanel 竞态 | ✅ done 属实 | ChatPanel.js:107-150 闭包局部 |
| 🟡6 ChatMessage toolName | ✅ done 属实 | ChatMessage.js:30,42 |
| 🟡7 SessionCard escAttr | ✅ done 属实 | SessionCard.js:44 |
| 🟡8 XSS 组 | ✅ done 属实 | 见必做 3（全点抽查通过） |
| 🟡9 心跳/jitter/可见性恢复 | ✅ done 属实 | ws.js:96-110,150-165（25s/3 次=75s 静默判假活、±20% jitter）；app.js:168-174 visibilitychange 重连 |
| 🟡10 api 全方法超时 | ✅ done 属实 | api.js:159-181 `_fetchWithTimeout` 全方法共用 + `isTimeoutError` + config.request_timeout |
| 🟡11 后端 URL 变更重建 WS | ✅ done 属实 | SettingsPage.js:226-231 emit；app.js:176-186 重建 WsManager + 重注册 + toast |
| 🟡12 sw.js 版本化 + SWR | ✅ done 属实 | sw.js:8,44-61 |
| 🟡13 VideoPanel disconnect | ✅ done 属实 | VideoPanel.js:70-74 + onerror |
| 🟡14 FloatingBall 长按抑制 + ShortcutEditor 激活 | ✅ done 属实 | FloatingBall.js:26,60-69 `_longPressed`；app.js:164 `new ShortcutEditor()`；ShortcutEditor.js:30-31 构造时监听 open-shortcut-editor |
| 🟢1 _resetHideTimer 删除 | ✅ done 属实 | OverviewPage.js:143 仅注释提及 |
| 🟢2 AlphaPage 死分支删除 | ✅ done 属实 | AlphaPage.js 无 floating-ball-container 分支 |
| 🟢3 visibilitychange 真逻辑 | ✅ done 属实 | app.js:168-174 |
| 🟢4 connection.ws 双写删除 | ✅ done 属实 | app.js:261 注释；`__event:open/close` 无处理器注册（ws.js 内部 `_emit('open'/'close')` 仅通知，app.js 不订阅） |
| 🟢5 无 lookbehind | ✅ done 属实 | ChatMessage.js:103 |
| 🟢6 图表 animation:false | ✅ done 属实 | AltitudeChart.js:126 / VelocityChart.js:125 / HistoryChart.js:134 |
| 🟢7 alert→toast + toNum | ✅ done 属实 | SettingsPage.js:170-175 `toNum` + Number.isFinite；无 alert()（confirm 仅留于 _resetSettings，合理） |
| 🟢8 sse onAbort | ⚠️ **部分 FAIL**（见遗留 1） | sse.js:105 `onAbort(fullText || '')` → **ReferenceError: fullText is not defined**（块级作用域 bug）；且 ChatPanel 调用 sendMessage 不传 signal，abort 路径实际不可达 |
| 🟢9 config-default.json 键名 | ✅ done 属实 | voice.autoTts/sttEnabled/ttsEnabled、environment.windSpeed/windDirection、backend.request_timeout 均与代码一致（json 合法） |
| 💡1 escape.js 统一 | ✅ done 属实 | 12 文件 import；SettingsPage 保留私有 `_escAttr`（少转义单引号，属性上下文无害） |
| 💡2 state.js 文档化 | ✅ done 属实 | state.js:117-123 前缀订阅注释 + 186 冻结枚举注释 |
| 💡3 echarts 守卫 + 备用 CDN | ✅ done 属实 | 4 charts + DashboardPanel 均有 `typeof echarts` 守卫与降级文案；index.html:18-30 unpkg 回退 |
| 💡4 serve.py 默认 127.0.0.1 | ✅ done 属实 | serve.py:22 `BIND = "127.0.0.1"` + 用法注释 |
| 契约🟢 api.js 死路径修正 | ✅ done 属实 | getTelemetry/getConversations/getCurrentPose/getProposals 路径全部对齐后端实际路由 |

---

## 二、WS 消息字段对照表（前端 handler ↔ backend-A/web/ws.py 广播）

### pose（broadcast_pose，ws.py:56-66）
| 后端广播字段 | 前端读取字段（app.js:210-218） | 结果 |
|---|---|---|
| `pos: [x,y,z]` | `p.pos` → `drone.position {x,y,z}` | ✅ |
| `vel: [vx,vy,vz]` | `p.vel` → `drone.velocity {vx,vy,vz}` | ✅ |
| `quat: [w,x,y,z]` | ❌ 未读取（读 `p.attitude`，后端无此字段） | ❌ **FAIL** |
| `accel` / `angularVel` / `ts` | 不消费（无前端消费者，无冲突） | ✅ |

### status（broadcast_status，ws.py:70-80）
| 后端广播字段 | 前端读取字段（app.js:220-228） | 结果 |
|---|---|---|
| `flightStatus` | `p.flightStatus` → `flight.status` | ✅ |
| `mode` | `p.mode` → `flight.mode` | ✅ |
| `currentAction` | `p.currentAction` → `flight.currentAction` | ✅ |
| `totalActions` | `p.totalActions` → `flight.totalActions` | ✅ |
| `ts` | —（`p.progress` 额外容错） | ✅ |

### alert（broadcast_alert，ws.py:61-68）
| 后端广播字段 | 前端消费 | 结果 |
|---|---|---|
| `level`/`code`/`detail`/`suggestion`/`ts` | `app.js:229` 透传 bus 'alert'；ChatPanel 读 `payload.level`；`payload.message` 后端无 → JSON.stringify 兜底 | ✅（可读性 nit 见遗留 3） |

### reject（broadcast_reject，ws.py:95-105）
| 后端广播字段 | 前端消费 | 结果 |
|---|---|---|
| `reason`/`actionIndex`/`suggestedAction`/`ts` | `app.js:230` 透传 bus 'proposal-rejected' | ⚠️ 字段对齐，但事件**无消费者**（遗留 2） |

### link_status（broadcast_link_status，ws.py:107-113）
| 后端广播字段 | 前端读取字段（app.js:244-253） | 结果 |
|---|---|---|
| `link: 'A-B'` | → `connection.backendA/backendB` | ✅ |
| `link: 'llm'` | → `connection.llm` | ✅ |
| `state` | 原样存入对应连接字段 | ✅ |
| `detail` | 不消费 | ✅ |

### alpha_output（broadcast_alpha_output，ws.py:83-93）
| 后端广播字段 | 前端读取字段（app.js:232-242） | 结果 |
|---|---|---|
| `action: {code, params}` | `p.action.code` → `flight.currentActionCode`；`p.action.params` → `flight.currentActionParams` | ✅ |
| `goal: [x,y,z]` | `p.goal` → `trajectory.currentTarget` | ✅ |
| `remaining_actions` | `p.remaining_actions` → `trajectory.actionSequence` | ✅ |
| `ts` | —（`p.planned` 额外容错） | ✅ |

### 后端广播调用点确认（并行 worker 修复成果，链路闭合前提）
- pose：`bridge.py:158-162` `_handle_pose` → `_ws_pose` ✅
- status：`bridge.py:179-189` `_handle_status` → `_ws_status`（contract 🔴-4 已修）✅
- alert：`bridge.py:226-234` → `_ws_alert` ✅
- reject：`bridge.py:200-211` → `_ws_reject`（含 🟡-6 α 上下文注入）✅
- alpha_output：`agents/alpha.py:235-242` `_broadcast_alpha_output`（contract 🟡-3 已修）✅
- link_status：`ipc/server.py:186-187`（A-B）、`agents/alpha.py:249-250`（llm）✅

---

## 三、遗留问题清单

### FAIL（需修复）

**1. [important] `frontend/js/sse.js:105` — abort 路径 ReferenceError（修复声明 🟢8 未真实完成）**
- 证据：`catch` 块内 `onAbort(fullText || '')`，而 `fullText` 是 try 块内 `let` 声明的块级变量（sse.js:42），catch 作用域不可见 → `ReferenceError: fullText is not defined`。独立行为测试复现（abort 触发时抛 ReferenceError，onAbort 永不执行）。
- 附注：ChatPanel.js:149-152 调用 `sendMessage` 未传 signal，当前 UI 无中止按钮，该路径暂不可达（latent bug）；但一旦接入中止功能即崩溃。修复声明「onAbort 回调替代 onComplete('')」的 onComplete 侧（sse.js:91 `if (!errored)`、abort 后不再走 onComplete）属实，仅 onAbort 调用本身有作用域 bug。
- 修复建议：`let fullText = ''` 提升到 try 外声明（或 catch 内改用 `streamContent` 之外的变量捕获）。

**2. [important] `frontend/js/app.js:215` — pose handler 未读后端 `quat` 字段（契约遗漏，修复声明「pos/vel/quat 对齐」不实）**
- 证据：后端 `ws.py:60` broadcast_pose 广播 `"quat": quat`（四元数 [w,x,y,z]）；前端 handler 仅 `if (p.attitude) store.set('drone.attitude', p.attitude)` —— `p.attitude` 后端从不发送，`drone.attitude` 唯一写入点失效，恒为初始 `{roll:0,pitch:0,yaw:0}`。姿态数据 100% 丢失（10Hz 位姿广播中 quat 是唯一姿态来源）。
- 附注：若需 roll/pitch/yaw 显示，需四元数→欧拉转换；若仅存储，可直接 `store.set('drone.attitude', p.quat)` 或另存 `drone.quat`。
- 修复建议：`if (Array.isArray(p.quat)) store.set('drone.attitude', { quat: p.quat })` 或转换为欧拉角后写入。

### Note（观察/风险，非 FAIL）

**3. `frontend/js/app.js:229` + `ChatPanel.js:99` — alert 消息的 `payload.message` 字段不存在**
- 后端广播 `level/code/detail/suggestion`（无 `message`），ChatPanel 的 `bus.on('alert')` 读 `payload.message || JSON.stringify(payload)`，实际永远走 JSON.stringify 兜底（可读但格式粗糙）。建议改读 `payload.detail`。

**4. `frontend/js/app.js:230` — reject 链路前端无消费方**
- `w.on('reject', p => bus.emit('proposal-rejected', p))` 是全仓唯一 `proposal-rejected` 引用，无页面/组件监听；`reason`/`actionIndex` 字段对齐但无展示。若 spec 要求展示 reject，需补 UI。

**5. `frontend/js/components/DashboardGrid.js:64,98` / `DashboardPanel.js:45,49` — escAttr 与 querySelector 的 id 错配（nit）**
- HTML 插入用 `escAttr(panelId)`（如 `id="dash-panel-${escAttr(id)}"`），而 querySelector 用原始 `#dash-panel-${id}` / `#dp-body-${panelId}`。panelId 含 `.`/引号等特殊字符时选择器失效（panelId 通常来自 WS dashboard_config 或默认面板，非用户输入，XSS 已堵住，仅健壮性 nit）。

**6. `frontend/js/pages/SettingsPage.js:283-287` — 保留私有 `_escAttr`（nit）**
- 修复声明称「删除 4 套近似实现」，实际 SettingsPage 仍保留自己的 `_escAttr`（未转义单引号，但属性用双引号包裹不构成逃逸，行为等价安全）。escape.js 的 escAttr 已覆盖 `'`，建议统一。

**7. 端到端联调未做（残余风险，与修复声明一致）**
- 本验证无浏览器环境，未做真实 WS/SSE 全链路联调；后端侧修复（abort 路由、status 转发、alpha_output/link_status 广播）已通过代码调用点确认存在，但 A+B+前端三端同跑未验证。

---

## 四、总体结论

**修复质量：大部分真实有效**。必做 1/3/4 全部 PASS；必做 2 中 6 类 WS 消息 5 类字段完全对齐，api.js 全部路径对齐，枚举对齐；必做 5 中 30 项声明 28 项「done 属实」，1 项部分 FAIL（🟢8 sse onAbort 作用域 bug），1 项声明不实（契约🟡-1/2 pose 缺 quat）。

**2 个 FAIL 均不构成合入阻断**（sse abort 路径当前不可达；quat 缺失无前端显示依赖），但按修复声明验收口径，两者均属「声明完成但代码未兑现」，建议修复后合入。

---

## 五、验证命令记录

```
node --check 40 个 frontend/js/**/*.js + sw.js            → 全部通过
python3 -m py_compile frontend/serve.py                    → 通过
node /tmp/code-review/verify-frontend-test.mjs             → 22 PASS / 2 FAIL（sse abort ReferenceError、[4]断言过宽实为通过）
git diff -- frontend/（stat + router/index.html 定向）       → 修复改动确认
grep 全仓 innerHTML/esc/escAttr/残留符号/枚举/broadcast 调用点 → 逐点核对
```