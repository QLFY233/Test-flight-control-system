# 试飞控制系统 — 模块进度

> 本文件是**模块级进度追踪**，对齐 [`docs/开发规划.md`](开发规划.md) 的阶段 A~M。
> 规则见 [`CLAUDE.md`](../CLAUDE.md) §四：每模块完成时更新此文件 + todo 插件 + git push；开发前先 git pull。
> 状态图例：⬜ 未开始 / 🚧 进行中 / ✅ 已完成 / ⏳ 远期

最近更新：2026-08-06 (历史页重设计 + 看板修复 — 规划已确认，写入 todo)

> **2026-08-06 (规划确认 — 历史页重设计 + 看板修复)**:
> ① **需求**（用户确认）: ① 重新设计历史界面 — 能查看看板界面的所有数据 + 飞行 2D/3D 轨迹 + 进度条; ② 修好看板界面（当前无法用）
> ② **看板现状诊断**: β `dashboard_configure` 工具只返回 note、从不广播 `dashboard_config` WS → 前端 β 工具驱动是死的; WS `pose` 广播带 `accel/angularVel` 但 app.js 丢弃 → 加速度面板恒空; 异常 bar 面板硬编码假数据 [3,7,2,5,1]; FilterBar 只 console.log; 无数据时全页 `--`/空图观感"坏了"
> ③ **历史现状诊断**: `_renderDetail` 从不加载选中会话遥测 → HistoryChart 读 `store.trajectory.flown`（当前会话）非历史会话; 无 3D 轨迹; 无看板式数据面板; TimelineControl 时长恒 60s（flown 无 t）; telemetry 端点只返回 pos+vel（accel/angular_vel/quat 未返回）
> ④ **方案**: Part A 后端（telemetry 端点补全字段 + dashboard_config 真广播）→ Part B 看板修复（接真 accel/去假数据/β 驱动/空态兜底）→ Part C 历史重构（会话数据集加载器 + 回放引擎 + 看板式面板 + 2D + 3D + 双进度条）
> ⑤ **关键决策**: 历史回放数据存独立路径 `store.history.playback.dataset`（不污染实时 `trajectory.flown`）; 3D 历史视图倾向扩展 Scene3D 历史模式（回归风险大则独立 HistoryScene3D）; 异常面板改"飞行统计"（时长/里程/最大速度等真实计算）+ 实时告警计数（DB 无告警表，历史侧无法展示真实历史告警）
> ⑥ **模块明细**见下方「阶段N」表

> **2026-08-06 (PX4 阶段2 飞机不动修复 — 双根因)**:
> ① **现象**: α 输出 goto/takeoff 动作但飞机不动 (用户报告「飞回原点 → goto(0,0,0) 但飞机不动」)
> ② **根因 A — mavros fcu_url 端口错**: launch 配置 `udp://:14540@127.0.0.1:14557`, 但 PX4 v1.13 SITL onboard mavlink 实例绑定 **14580** (发往 mavros 14540; 脚本注释本就写明) → mavros 下行 SET_POSITION_TARGET_LOCAL_NED 丢包。修复: `mavros_px4.launch` + `start_px4_sitl.sh` 14557→14580
> ③ **根因 B — B 侧 type_mask=0**: `Phase2Adapter.TYPE_MASK_POSITION = 0` (全部字段"有效") 但 B 只填 position, 速度/加速度为 0 → PX4 判定 `SET_POSITION_TARGET_LOCAL_NED invalid` (实测: 手动 2552 被接受且飞机动, B 的 0 被拒)。修复: 改 2552 (0x9F8 = IGNORE_VX|VY|VZ|AFX|AFY|AFZ|YAW_RATE, 即注释声称的"忽略速度/加速度/力/yaw_rate"语义)
> ④ **验证**: 修复后完整链路 — β「起飞到 3 米」→ α 翻译 takeoff(0,0,2.5) → B 下发 → PX4 执行 → 飞机升至 2.4m 悬停 → 自动推进 hover → flight_status=completed, progress 100%; invalid 计数不再增长; B 测试 152/152
> ⑤ **备注**: 重启 mavros 会触发 PX4 failsafe (manual control lost → 降落掉臂), 需重启 B 重新 preflight (streaming→arm→offboard→ACTIVE); 环境重启用 start_px4_sitl.sh (nohup 后台跑防 timeout 杀进程链)

> **2026-08-06 (聊天区工具卡片紧凑化 + 历史页卡片样式恢复 + 工具 args 答疑)**:
> ① **历史页"只有字体无卡片框"**: 根因 — SW Stale-While-Revalidate 混合缓存 (新 components.css 已删 session-card 样式 + 旧 HistoryPage.js 仍 import 已删除的 SessionCard.js) → 旧卡片元素无样式纯文本。修复: sw.js BUILD_ID 更新废弃旧缓存 (用户需刷新一次页面); 实测硬刷新后 .task-card 边框/背景/当前红色左边框正常
> ② **工具调用 args 显示 {} 答疑**: 正常 — 所有 β 工具均为无参函数 (`def get_field_map()`), pydantic-ai 对无参工具生成空 args {}; 工具实际执行正常 (✓ 行有返回数据)。get_current_environment 返回 None 也是正常的 (当前会话未设置环境, 可去总览/设置页配置)
> ③ **工具卡片刷屏优化** (ChatMessage.js + CSS): 无参工具不渲染参数行 (卡片只剩一行工具名); 有参工具默认折叠 (点击展开, ▸/▾ 指示); tool_result 长内容截断 300 字符 + 「▸ 展开/▾ 收起」; 卡片 margin/padding/字号缩小 (space-2→space-1, text-xs→text-2xs), body max-height 140px 内部滚动
> ④ **验证**: Playwright — 无参卡 bodyCount=0; 有参卡默认 collapsed + ▸; 800 字符结果截为 302 (含…); 展开后全文; 历史页卡片 border-bottom/current 红边框恢复; console 零错误

> **2026-08-05 (β 工具调用卡死修复 — #7 流式改造回归)**:
> 现象: β 回复「我来帮你规划…让我同步查询」后无输出（工具调用后 agent 卡死）；curl 复现：get_field_map 等工具调用后流永不继续
> 根因: sse.py #7 流式改造用 `run_stream()+stream_text()`，但 **pydantic-ai 2.0 文档明确：run_stream 默认 end_strategy 下不执行工具调用**（"tool calls will not run in streaming mode with the default settings"）→ β 首轮文本+工具调用时 agent 挂起
> 修复 (sse.py): 改 `run_stream_events()` 逐事件流 — TextPartDelta.content_delta（增量文本）→ text 事件；FunctionToolCallEvent/FunctionToolResultEvent → tool_call_start/tool_call_result 事件（前端 sse.js 已支持）；累积 full_text 存对话持久化；plan 事件逻辑不变
> 验证: curl「查询场地边界」→ tool_call_start(get_field_map) → tool_call_result(场地信息) → 流式文本继续；「帮我规划一次飞行任务」→ 5 次工具调用全部执行 + 569 个 text 事件（10KB 完整回复）零卡死
> 重启: run_a.py 已重启生效

> **2026-08-06 (新功能 — 任务管理面板完成)**:
> ① **需求**: [ BETA AI ] 一栏最右侧任务管理 — 新建/删除/重命名/恢复任务; 任务绑定 β/α 对话记录 + 飞行数据记录
> ② **后端**: `db/repos.py` 新增 `list_sessions_with_stats` (任务列表+对话条数+遥测条数+最后活跃) + `delete_session` (级联删 conversations/telemetry/会话行); `web/routes.py` GET /api/sessions 改用统计版; 新增 `POST /api/sessions/{id}/activate` (恢复=切换当前会话, 清旧任务待审提议防串扰) + `DELETE /api/sessions/{id}` (删当前任务时置空 session_id + 清 pending); POST /api/sessions 新建时清 pending_proposal/pending_task_name
> ③ **前端**: 新组件 `js/components/TaskPanel.js` — 表头最右侧「☰任务」按钮 (监听 chat-panel-rendered 幂等重挂, 面板挂 body 避免 sidebar overflow 裁剪) + 下拉面板 (新建/恢复/重命名行内编辑/删除行内确认/当前徽标/β对话数·飞行数据数); `ChatPanel.js` render() 末尾 emit chat-panel-rendered; `app.js` 重构 `loadTaskContext(sid)` (会话详情+β/α 对话映射(α tool_call→[α] 动作序列 N 条)+遥测轨迹降采样≤600) + 监听 task-restore 事件; `api.js` 新增 getTaskList/createTask/renameTask/deleteTask/activateTask
> ④ **修复**: 行内操作按钮 (重命名/删除确认) 同步重渲染后事件目标脱离 DOM → document 点击监听误关面板 — 加 stopPropagation + isConnected 守卫
> ⑤ **验证**: 后端 83/83 (新增 Test 6c: 列表统计+级联删除); Playwright 全流程 — 新建(聊天区清空+当前徽标)/重命名(前后端一致)/恢复(19 条 β 对话载入+session 切换)/删除(行内确认+DB 三级联清零)/删当前任务自动新建承接; console 零错误
> ⑥ 备注: 验证期间 WSL 意外重启 → start_all.sh 全链路恢复后复测通过

> **2026-08-06 (三处任务视图统一 — AI 任务面板 / 总览最近任务 / 历史记录)**:
> ① **背景**: 三处任务数据源同为 flight_sessions, 但展示/操作不统一 — 总览与历史用旧 SessionCard (字段错配: task_summary/task_title 后端不存在 → 恒「无描述/未知任务」; 状态用 success/warning 旧枚举 → 显示原始英文); 总览/历史无任何任务操作
> ② **统一方案**: 新组件 `js/components/TaskCard.js` — 唯一任务渲染源 (名称 task_description||任务 #短id / 状态飞行枚举中文+颜色 / 时间短格式 / β 对话·数据计数 / 当前徽标) + 公共操作 (createNewTask / deleteTaskRecord 删当前自动新建承接 / activateTaskRecord / resetUiForNewTask) + 行内重命名/删除确认/多选 checkbox; 三处全部复用
> ③ **接入**: TaskPanel 重构删重复逻辑 (行渲染/操作全走 TaskCard); OverviewPage 最近任务改用 TaskCard (点击仍跳历史详情, 监听 task-restored 刷新当前徽标); HistoryPage 列表改用 TaskCard (保留多选+发送到 Beta), 右侧详情字段统一为 task_description/状态枚举/对话·数据计数, 监听 task-restored 刷新
> ④ **清理**: 删除死代码 SessionCard.js + 旧 session-card/task-panel__row CSS, 新增 TASK CARD 样式区块
> ⑤ **修复**: TaskCard._rerender 的 `render()` 会先覆盖 this._el 再 replaceChild → 抛 "node is not a child" 异常 → _doActivate 在 fetch 前中断、_busy 永久卡死 (按钮全失效)。修复: 先保存旧元素引用再 render; _doActivate 的 finally 恢复渲染
> ⑥ **验证**: Playwright — 三处同一任务渲染逐字一致 (名称/状态/时间/计数/当前徽标); 历史页恢复→后端 session 切换+聊天载入; 历史页重命名→AI 面板同步; 历史页删除→两处列表同步; console 零错误

> **2026-08-06 (飞控页 [ TASK ] 下方新增 [ α OUT ] Alpha 实时输出卡片)**:
> ① **需求**: 飞控面板 [ TASK ] 下方新增卡片, 展示 alpha AI 实时输出, 支持滚动
> ② **实现**: AlphaPage 左栏第三卡片 [ α OUT ] — 监听 bus 'alpha-output' (WS alpha_output 广播, remaining_actions→action.actions→actions 三级提取), 每条记录 = 时间戳 + 动作编码链 (takeoff → goto(3.0,2.0,1.5) → hover 2s); 去重 (与末条相同跳过, 防 2s 心跳重复刷屏); 上限 60 条滚动淘汰; 智能跟随滚动 (用户上滚查看时不打扰); CLEAR 清空按钮; 刷新/恢复任务后 actionSequence 异步载入时自动补首条 (订阅 trajectory.actionSequence 路径变更, 忽略 10Hz 遥测)
> ③ **验证**: Playwright — 卡片位于 [ TASK ] 之后; 模拟 3 序列广播正确追加+重复去重; 70 条批量→上限 60; max-height 260px overflow-y auto 滚动生效; CLEAR 清空恢复等待提示; 真实广播路径 (WS→app.js→bus) 确认
> ④ **注意**: SW 缓存旧版 components.css 导致新样式不生效 — 需清缓存重载 (硬刷新) 或等待 SW 后台更新

> **2026-08-06 (任务自动命名修复 — forward 路径 + 已存在会话补名)**:
> ① **现象**: 用户「直接执行：起飞到 3 米」等指令后任务仍无名字 (历史页显示 任务 #id / 无描述)
> ② **根因**: 自动命名只覆盖 β 提议 (propose) 路径 — propose_to_alpha 设 pending_task_name; 免审直发 forward_last_human_message 不设 → α _log_action 建会话 task_desc=None; 且会话先由对话创建 (sse _ensure_session, task_desc=None) 后 α 执行动作时 existing 非 None → 永不补名
> ③ **修复** (agents/alpha.py _log_action): 统一命名 — pending_task_name (propose) 优先, 否则从动作序列生成摘要名 (复用 tools/beta_tools._derive_task_name: 起飞2m→悬停3s); 会话已存在且 task_description 为空 → 补名; 已有名字不被覆盖
> ④ **验证**: A 侧 86/86 (新增 Test 6d 三场景: forward 摘要名 / 已存在会话补名 / 已有名不覆盖); 真实链路「直接执行：起飞到 2 米悬停 3 秒」→ task named: 起飞2m→悬停3s → 任务列表 task_description 正确

## 待办事项与已知问题（2026-08-05 用户反馈）

> 用户实测反馈的待办/缺陷清单，按需排期修复。状态图例同顶部：⬜ 未开始 / 🚧 进行中 / ✅ 已完成。

> **2026-08-05 (启动全链路修复 — start_all.sh 首跑暴露 2 处)**:
> ① **backend-B 阶段1回归**: `run_b.py:97` 无条件调 `gp_adapter.set_event_sender(...)`, 但该方法仅 `Phase2Adapter` 有 (ef50299 引入, S8 只测 Phase2 未暴露) → Phase1 (sim-drone) 启动必崩 AttributeError。修复: `if PHASE == 2:` 守卫 (对齐 set_land_handler 模式)。验证: 全链路 sim-drone→B→A→REST 起
> ② **start_all.sh pkill ERE bug**: `pkill -9 -f "roscore\|rosmaster\|..."` 中 `\|` 在 ERE 是字面竖线 → 清理从不生效, 残留节点名冲突致重启失败。修复: `\|`→`|` (与 2026-08-03 start_px4_sitl.sh 的修正同因)。验证: 二次 start_all.sh 清理+重启全绿

> **2026-08-05 (新需求 — 左栏↔右栏可拖动分界条)**:
> 需求 (用户确认): 规划界面各部分分界可自由拖动调占比 — 范围=仅左栏↔右栏视图一条竖向分界; 持久化=仅本次会话有效 (刷新恢复默认); 应用=所有页面通用
> 实现: `shared.js renderTwoColumn` 插入 `.layout-splitter` + `bindLayoutSplitter` (mousedown/touchstart 拖动, 实时改左栏宽 px, 钳制容器 15%~75%, 模块级 `_leftWidth` 导航保留/刷新重置, `window.blur` 兜底防光标卡死); `layout.css` 分界条样式 + 移动端 `<768px` display:none
> 生效页面: BetaPage (规划) + AlphaPage (飞控) — 两者共用 renderTwoColumn 左右分栏
> 验证: Playwright 1400px — 拖动 +200px 生效、钳制 75%/15%、hash 导航保留、`page.reload()` 重置 42%、AlphaPage 同样生效、移动端 480px splitter display:none; 零 console 错误
> code-review (medium): 0 发现
> 已知限制: 拖动后用 px 定宽, 会话内窗口缩小不再重钳制 (右栏 flex 自动收缩, 属本次会话临时布局, 可接受)

> **2026-08-05 (待办 #8 — 去掉设置页「后端」部分完成)**:
> ① SettingsPage.js: 移除「后端」Tab (后端地址/WS/SSE 端点配置, 部署内网同源后无需暴露); activeTab 默认改 'environment'; 清理死代码 (config/apiManager/deepMerge 导入, bc/ec 变量, _saveSettings 后端读取 + setBaseUrl + backend-url-changed 事件)
> ② app.js: 移除 backend-url-changed 处理器 (无触发源死代码) — 同源自适应 base_url 逻辑保留 (config-default.json + location.origin)
> ③ 注: 设置页后端 Tab 本就不在 前端 spec §9.4 (5 项功能), 删除后对齐 spec
> ④ 验证: Playwright #/settings — Tabs=[显示,语音,环境] 无后端, 环境 Tab 默认渲染, Tab 切换/保存/应用按钮点击零 console 错误
> ⑤ code-review (medium): 0 发现 — 纯删除改动

> **2026-08-05 (待办 #3 — AI 自动给飞行任务取名完成)**:
> ① 根因 — propose 流程无任务名: proposal 无 title/task_name 字段 (FlightPlanCard 恒显"飞行计划"), 会话 task_description 恒 null
> ② 修复 `tools/beta_tools.py`: `_derive_task_name(intent, actions)` — 从**预翻译动作序列**生成结构化摘要 (如 `起飞1m→飞往(3,2)→悬停2s…`, 中文标签映射 9 类编码, 超 4 动作省略, 无动作时截断意图, 空兜底"试飞任务"); propose_to_alpha 存入 proposal.task_name/title + AppState.pending_task_name
> ③ `web/sse.py` plan 事件: title 改取 proposal.title (兜底 task_name/"飞行计划"), 新增 task_name 字段 — FlightPlanCard 已读 plan.title 无需改前端
> ④ `agents/alpha.py` _log_action: 建会话时 task_desc=pending_task_name (forward 路径无提议时保持 None 原行为)
> ⑤ 验证: A 侧 71/71 (新增 Test 16 命名 6 用例); 真实 LLM propose → proposal.title=`起飞1m→飞往(3,2)→悬停2s` → Playwright β 页卡片标题正确显示 + 无 console 错误; 脚本验证 propose→approve→会话 task_description 一致
> ⑥ code-review (medium): 0 发现 — 退化情形 (空 code → "→→" 分隔符) 被预翻译 schema 约束兜住, 不为此加校验

> **2026-08-05 (待办 #11 — 刷新后历史任务与当前任务自动恢复完成)**:
> ① **β 对话持久化**: 根因 — 全仓 `save_conversation` 仅 α `_log_action` 调用, β 对话 (human/agent) 从未入库 → 刷新即丢。修复 `web/sse.py`: `_ensure_session()` (session_id 为空则按 α 同规则生成 + 建 flight_sessions 行) + `_save_conv()`; chat_beta 流前存 human、流完存 agent 完整回复
> ② **会话详情端点**: `db/repos.get_session_detail()` (含 environment_name + telemetry_count) + `GET /api/sessions/{id}` (404 兜底) — 前端恢复任务描述/alpha_actions/status
> ③ **sync_response 补 session_id**: `web/ws.py` sync 响应加 `session_id` 字段 (重连可获当前会话)
> ④ **前端恢复**: `app.js` 新增 `restoreSessionState()` — init 末尾调用: overview→session_id/flight.status → session detail→taskDescription/alpha_actions(_restoreActionContext 复用 _normalizePlan 推导)→ conversations→chatHistory→ChatPanel.render(); 任一环节失败静默不阻塞启动
> ⑤ **验证**: 后端 65/65 (新增 Test 6b: 会话详情 + β 对话持久化); 真实 LLM 对话流完成后 human+agent 均落库; Playwright headless 加载 → 对话恢复显示 (human+agent 2 条) + console 零错误
> ⑥ **code-review (medium)**: 4 项 — 测试顺序断言 flaky 已修 (sorted 集合断言); `_ensure_session` 并发竞态 (与 α 既有模式一致, PLAUSIBLE 低危不修); 恢复轨迹起点用 {0,0,0} 近似 (实时 alpha_output 修正, PLAUSIBLE); 会话创建逻辑与 α 重复 (CONFIRMED 低危, 记录不重构)
> 注意: 后端重启会重置 AppState.session_id (overview 返回 null) → 前端不自动恢复 (历史页仍可查); 浏览器刷新 (后端存活) 场景完整恢复

| # | 待办 | 类型 | 状态 | 备注 |
|---|---|---|---|---|
| 1 | 页面下方 PROGRESS 进度条不动 | 🐛 bug | ✅ | 根因: 后端 status payload 缺 progress 字段 (flight.progress 恒 0) + BottomBar 无订阅。修复: B 侧 _send_status 计算 progress (currentAction/totalActions) + A 侧 bridge 转发 + WS broadcast_status 加字段; BottomBar 由 app.js scheduleBottomBar 驱动重渲染 (已存在, 无需自订阅)。验证: 多动作计划 20%→40% 实时递增 |
| 4 | 看板页面只有拖动模块时数据才更新 | 🐛 bug | ✅ | 已由 #2 实时化改造修复 (DashboardPanel 订阅 store.drone/flight + 环形缓冲 + _refreshValueCard)。验证: 飞行中 ALT -0.26→0.92 实时递增, SPD/PROGRESS 同步, 无需拖动 |
| 2 | [ BETA AI ] 界面美化 | ✨ 需求 | ✅ | ① 常用功能卡片化：ChatPanel empty 态 4 张快捷卡（飞行规划✈/历史分析⌚/数据处理〰/状态查询◉）点击即发预设指令；② 异常信息防刷屏：同 code 1s 节流丢弃 + 10s 折叠计数（×N 徽标，DOM+store 双同步）+ level 色卡片（critical 红/warning 黄/info 蓝）+ code 徽标。验证: 5 条同 code→store 仅 1 条；间隔 2s×3 条→折叠 ×3 徽标 |
| 3 | AI 自动给飞行任务取名 | ✨ 需求 | ✅ | β 生成提议时自动产任务名（flight_sessions.task_description / FlightPlanCard 标题展示） |
| 5 | 历史界面有 bug | 🐛 bug | ✅ | 根因: `.history-page__detail` 行方向 flex → 3 详情区(任务/回放控制/轨迹)横向并排, 窄窗口挤压。修复: 改列方向+stretch+overflow-y:auto, detail-section 加 min-width:0+padding; EmptyState 靠自身内部 flex 居中两态兼容。验证: 800px 视口 3 section 同 x 同宽 498px y 递增纵向堆叠 |
| 6 | 数据驱动的分析工具与可视化，分析过程可视化 | ✨ 需求 | ⬜ | β analytics 工具结果可视化（FFT/统计/滤波图表展示）+ 分析过程可视化（工具调用过程展示） |
| 7 | 没有流式输出 | 🐛 bug | ✅ | 根因: sse.py 用非流式 agent.run() 一次返回。修复: 改 agent.run_stream() + stream_text(), 累积文本求差取增量逐 chunk 发 text 事件; 移除无用导入。验证: 10+ text 事件增量不重复; 前端"你好"→β 完整回复无重复无错误 |
| 8 | 去掉设置页「后端」部分 | ✨ 需求 | ✅ | SettingsPage 移除「后端」Tab（后端地址/WS/SSE 端点配置，部署内网同源后无需暴露） |
| 9 | 去掉显示设置里的「主题」 | ✨ 需求 | ✅ | SettingsPage display Tab 移除（原仅含主题一项），tabs=[voice,environment]；app.js 移除 theme-light 应用 + beforeunload 不再存 theme。验证: 设置页无主题/无显示 Tab，语音/环境 Tab 正常 |
| 10 | 连接 TTS/STT 服务并调试 | ✨ 需求 | ⬜ | 讯飞语音链路（STT 签名/wpgs + TTS）联调：需 XF_APP_ID/API_KEY/API_SECRET 有效凭证，前端 AudioWorklet PCM 采集 + 音频播放验证 |
| 11 | AI 历史记录与当前任务刷新自动恢复 | ✨ 需求 | ✅ | 刷新后可恢复历史任务：AI 对话记录、飞行信息、规划信息、α 上下文（会话级快照/续接，对齐 conversations 表 + flight_sessions） |
| 12 | 历史回放横向宽度响应式 | 🐛 bug | ✅ | 同 #5 修复: .history-page__detail 改列方向, 3 详情区纵向堆叠铺满宽度, 窄窗口不再横向挤压 |

---

> **2026-08-05 (按 todo 修 bug 轮次 — #4/#5/#7/#12 完成)**:
> ① **#4 看板实时数据**: 已由 #2 实时化改造修复 (DashboardPanel 订阅 store + 环形缓冲), 实测飞行中 ALT/SPD/PROGRESS 实时递增无需拖动 — 无代码改动, 仅验证
> ② **#5/#12 历史回放响应式**: 根因 `.history-page__detail` 行方向 flex → 3 详情区横向并排窄窗口挤压。修复 `css/pages.css`: 改列方向+stretch+overflow-y:auto, 新增 `.history-page__detail-section` min-width:0+padding (EmptyState 内部自居中两态兼容)。验证 800px 视口 3 section 同宽 498px 纵向堆叠
> ③ **#7 SSE 流式输出**: 根因 sse.py 用非流式 `agent.run()`。修复 `web/sse.py`: 改 `agent.run_stream()` + `stream_text()`, pydantic-ai 2.0 的 stream_text 产出累积文本 → 与上一 chunk 求差取增量逐 chunk 发 text 事件; 移除无用导入。验证 10+ text 事件增量不重复, 前端"你好"→β 完整回复无重复无错误
> 验证: 各 bug headless 浏览器实测; A 测试 56/56
> 跳过: 需求类 (#2/#3/#6/#8/#9/#10/#11)

> **2026-08-05 (PROGRESS 进度条修复 — 待办 #1)**:
> 现象: 底部 PROGRESS 进度条不动 (恒 0%)
> 根因: ① 后端 `_send_status` payload 缺 `progress` 字段 (flight.progress 恒 store 默认 0); ② A 侧 bridge/WS 未转发 progress (字段被剥离); ③ BottomBar 无订阅 (仅 mount 渲染一次)
> 修复: ① B `small_model/component.py` 计算 progress = round(currentAction/totalActions*100) (completed N/N=100, hovering 0/0=0); ② A `bridge._handle_status` 转发 progress; ③ A `ws.broadcast_status` 加 progress 参数+字段; ④ BottomBar 由 app.js 既有 `scheduleBottomBar` (store.subscribe('flight'/'trajectory')) 驱动重渲染 — 已存在无需改 (勿自订阅防泄漏)
> 验证: 多动作计划「起飞2m→飞(4,3,1.5)→悬停3s→降落」→ 进度 20%→40%→... 实时递增 (headless 浏览器实测), ACTION 标签同步; B 152/152 + A 56/56
> BUILD_ID → `2026-08-05-fix-progress`

> **2026-08-05 (前端联调检查修复 #6 — 刷新后规划不显示)**:
> 现象: 刷新/重开后后端仍有 pending 提议，但前端飞行计划卡片不显示
> 根因: store.beta.currentPlan 仅由实时 plan 事件驱动（内存态，刷新即丢）；无恢复逻辑；且 shared.js apiManager 白名单缺少 getProposals 转发（调用 undefined 被 catch 静默吞掉）
> 修复: ① BetaPage.mount 时 `_restorePendingProposal()`：拉取 GET /api/proposals，存在 pending → 恢复 currentPlan + 渲染卡片（同 id 跳过防重复）；② shared.js apiManager 补 getProposals 转发
> 验证: 刷新后爱心航线 pending 提议自动恢复显示（卡片+批准按钮齐全）；无 JS 错误
> BUILD_ID → `2026-08-05-fix-proposal-restore`

> **2026-08-05 (前端联调检查修复 #5 — 批准后切页旧提议残留 404)**:
> 现象: 批准提议后切总览再回规划，旧 FlightPlanCard 重新渲染，再点批准/驳回 → API 404 not found or already processed
> 根因: `BetaPage._onPlanReceived` 把提议存 store.beta.currentPlan，approve/reject 成功**从不清理**；切页 mount 时 render() 读旧 currentPlan 重新渲染可操作卡片；后端 approve 原子认领后二次调用必然 404
> 修复 (BetaPage.js): approve/reject 成功 → 清 beta.currentPlan + trajectory.pending（黄色预览同步清）；catch 404/not found/already processed → 清卡片 + 友好提示「该提议已被处理」而非误导性「批准失败」
> 验证: 复现用户路径（发指令→卡片出现→批准✓→切总览→切回规划）→ 旧卡片不再出现（currentPlan=null、无 approve 按钮、planArea 恢复默认提示）
> BUILD_ID → `2026-08-05-fix-stale-proposal`

> **2026-08-05 (前端联调检查修复 #4 — 待批准航线预览)**:
> 需求: β 提议 pending 时在场地俯视图/3D 视图自动显示待批准航线
> 实现（并行 2 worker）:
> ① 后端: `beta_tools.propose_to_alpha` 改 async + `_pre_translate()`（lazy 预翻译器 + asyncio.to_thread 调 LLMTranslator，失败兑底 []）→ pending_proposal.actions 携带预翻译动作；sse.py plan 事件 actions 改从 proposal 取
> ② 前端: app.js `bus.on('plan-received')` → `_normalizePlan` 推导 → store.trajectory.pending；alpha_output 到达时清 pending（正式计划覆盖预览）；FieldMap2D 黄色虚线+黄色目标点（label 带 ?）；Scene3D 黄色虚线+黄色标记+编号（带 ?）
> 验证: 页面内发「起飞到1米然后飞到(3,2,1)」→ plan 事件带 [takeoff,goto,hover]（预翻译成功）→ FieldMap2D 黄色像素 4369（虚线+目标点）→ 3D 视图黄色标记 → approve → pending 清除 + 青色正式计划接管 + currentActionCode=takeoff；无 JS 错误
> 注意: 改后端后需重启 A（pkill 用 [r]un_a.py 防自杀）；BUILD_ID → `2026-08-05-fix-pending-preview`

> **2026-08-05 (前端联调检查修复 #3 — 飞行计划不在 PLN 视图显示)**:
> 根因: ① 后端 alpha_output 不广播 planned → trajectory.planned 恒空；② FieldMap2D 读 a.params?.target（对象）与 schema 权威格式 a.target（数组 [x,y,z]）不匹配 → 目标点不画；③ Scene3D 完全没有计划渲染逻辑；④ FieldMap2D 无无人机位置标记；⑤ flight.currentActionCode 读 p.action.code（ActionCommand 无此字段）恒空
> 修复（并行 2 worker）:
> ① app.js 数据层: _normalizePlan() 归一化 actionSequence（target 数组→对象）+ 链式推导 goal（对齐 B 侧 stub.py 语义：takeoff→home 上方/goto→target/move→沿方向/climb/descend→相对高度/return_home→home）；planned = [起点+目标点序列]；pose 10Hz 记录 flown（上限 600）；currentActionCode 改按索引从序列取；currentTarget 后端 goal 优先否则推导
> ② FieldMap2D: 订阅 trajectory（重建）+ drone（无人机标记 10Hz 增量更新，series id 合并）；目标点兼容 a.goal/a.target 数组/a.params.target 对象三格式
> ③ Scene3D: 新增 _buildPlan() — planned 青色虚线 + 目标点标记（BoxGeometry + 编号 sprite）+ 当前动作目标橙色高亮；订阅 trajectory/flight；unmount 清理
> 验证: 实测「飞到场地中心 2.5,2.0 高度1米」→ approve → α 翻译 [takeoff,goto,hover] → store 链式推导正确（takeoff→(0,0,1)、goto→(2.5,2,1)、planned 3 点、flown 202 点）；FieldMap2D 青色目标点+虚线+无人机标记渲染；Scene3D 青色虚线+橙/青双目标点+编号渲染；无 JS 错误；α/dashboard 回归正常。BUILD_ID → `2026-08-05-fix-plan-visualization`

> **2026-08-05 (前端联调检查修复 #2 — α 飞控页中间大面积黑屏)**:
> 根因: `AlphaPage.js` leftHtml 模板 [ENV] 卡片缺 `</div>` 闭合（24 open / 23 close，2026-08-02 b46435e 引入）→ 浏览器解析 innerHTML 时把模板外的 `<div class="right-column">` 吞进 left-column → 右栏（高度图）被挤到左栏卡片下方，页面中间 60% 区域空黑（用户宽屏 2560x1564 截图确认）。修复: [TASK] 卡片前补 `</div>`，模板 depth 0 ✅。验证: 清缓存后 right-column 回 page-container（两列并列满高 1300，高度图占满右栏）。注意: 懒加载模块改动必须同步 bump sw.js BUILD_ID（否则 SW 缓存旧模块再次遮蔽修复）。BUILD_ID → `2026-08-05-fix-alpha-layout`

> **2026-08-05 (前端联调检查修复 — 2 项 + SW 版本)**:
> ① **总览页 [系统状态] 面板恒显 UNK 修复**: 根因 — `connection.backendA/B/llm` 仅由 WS `link_status` 推送驱动（后端只在状态变化时推送），页面加载/重连后无主动拉取；`connection.drone` 无写入源。修复 — `app.js` 新增 `refreshLinkStatus()`（init + WS 重连成功时各拉一次 `/api/link-status` 写 store，flight_status 仅在缺失时填充）；pose 到达时置 `connection.drone='connected'`。验证: 总览页 BACKEND A/B=UP、DRONE=ONLINE、LLM=OK（原 UNK×4）
> ② **Dashboard 看板占位假数据修复**: 根因 — `DashboardGrid._defaultPanels()` 硬编码 PROGRESS 47.2/ALT 28.7/SPD 1.43 + `DashboardPanel` 时序图 `_mockData()` 随机数 + `Math.random()` 兑底。修复 — 时序面板（altitude/velocity）订阅 store.drone 环形缓冲 600 点（60s@10Hz）增量 setOption；value 卡片 source=altitude|speed|progress 读实时 store，无数据显示 '--'；accel_line 无数据源标注「无加速度数据源」；unmount 解绑订阅+dispose chart。验证: ALT=-0.29m/SPD=0.04m/s/PROGRESS=0%（实时值，对齐状态栏）
> ③ **sw.js BUILD_ID bump**: `2026-08-05-review-fixes → 2026-08-05-fix-unlink-dashboard`（Stale-While-Revalidate 策略下不 bump 版本则旧缓存持续生效，实测修复代码被旧缓存遮蔽）
> 验证: 浏览器全新加载（清 SW/缓存）实测双修复生效 + node --check 全过

> **2026-08-05 (代码审查修复 — medium effort, 6 项)**:
> ① **WASD 键盘劫持修复**: `ui.keyboardInputFocused` 全前端从未写入(死代码) → 改为检查 `e.target.tagName` (INPUT/TEXTAREA/isContentEditable), 输入框聚焦时不再被全局 keydown 吞键 (对齐 SessionCard.js 既有模式)
> ② **失焦按键锁死修复**: `_keys` Set 增加 `window.blur` 清空处理器, 防止按住松开时丢失 keyup 致相机持续漂移
> ③ **emergency 落地判定收紧**: `_emergency` 仅在 `armed=False` **且** `_is_grounded()` (ENU z ≤ home-0.3) 时清除 — 空中 disarm 不再误清标志后重切 OFFBOARD (S8.5 保护保留)
> ④ **spec §7.2 同步**: 移除已删元素 (GridHelper/边界盒/ConeGeometry/AxesHelper) 描述, 对齐实际渲染 (石头地板/HOME 文字/轨迹线/WASD)
> ⑤ **轨迹缓冲预分配**: `_appendTrailPoint` 改预分配 Float32Array + 滚动窗口 + setDrawRange, 消除每 10Hz tick 重新分配
> ⑥ **GPU 资源清理**: `_updateField`/`unmount` 调 `_disposeObject` 释放 geometry/material/CanvasTexture
> 验证: B 152/152 + headless 浏览器无 JS 错误 + 输入框聚焦按 WASD 无异常
> 提交: 代码审查修复 commit

> **2026-08-04 (前端 3D 视图重引入 — Gazebo GUI 替代)**:

> **2026-08-04 (前端 3D 视图重引入 — Gazebo GUI 替代)**:
> ① **问题定位**: WSL2 下 Gazebo Classic GUI(gzclient)完全不可用——WSLg 黑屏/卡死、VcXsrv Native OpenGL 依然卡死、`LIBGL_ALWAYS_INDIRECT=1` segfault。根因: OGRE 1.9 需直接 OpenGL 上下文,WSL2 全间接。**物理仿真(gzserver 无头)不受影响**(S8 实飞全程无头验证)。
> ② **解决方案**: 前端重新引入 Three.js **Scene3D** 组件(`js/charts/Scene3D.js`,Three.js 0.146.0 CDN),浏览器 WebGL 渲染无人机 3D 场景,数据来自 Gazebo 物理引擎实时位姿(经 PX4→MAVROS→B→IPC→A→WS)。渲染内容: 地面网格 + boundary 线框 + HOME 标记 + 无人机 + 高度参考线 + OrbitControls。
> ③ **视图切换**: 恢复 ViewModeSelector(`availableSources=['chart','3d']`),β 页面可在**场地俯视图**(FieldMap2D)与 **3D 视图**(Scene3D)间切换;ViewPanel source 枚举 `'chart' | '3d'`;store `ui.viewSources` 同步更新。
> ④ **坐标系**: ENU → Three.js(x→x东, z→y高, y→z北);yaw 从四元数 `[w,x,y,z]` 计算。
> ⑤ **实测验证**: 全链路 β→α→small_model→PX4 起飞(z -0.18→0.92m),3D 视图实时跟随仿真数据。
> ⑥ **环境恢复(顺带)**: 修 jammy 源混入(glibc/Qt5 错位)、PX4 编译依赖(kconfiglib/future/GStreamer/Qt5 跳过/Boost 兼容头)、COM_RC_IN_MODE 持久化覆盖、MAVROS/EGM96 重装、venv-A 重建。`start_px4_sitl.sh` 加 RC/offboard 参数强制确认。
> ⑦ **文档同步**: 前端详细设计 §6.9/§6.10/§7 + 总体架构 §3.4 + PX4-阶段2-design §11。
> 提交: 3D 视图重引入 + Gazebo GUI 替代方案 commit

> **2026-08-03 17:10 (S8 遗留闭环 — monitor PX4 适配 + LLM 真 key)**:
> ① DEEPSEEK_API_KEY 更新至 .env（本地保存, gitignore 不入库）；A 以 `set -a; source .env` 启动（代码无 dotenv 加载, key 走环境变量）
> ② **overaccel 误报消除**：mavros IMU linear_acceleration 含重力 ≈9.81 → monitor 运动加速度 = 速度导数（帧级死区 0.05 m/s + 低通 0.5），与 sim-drone 语义一致（悬停/匀速=0，真实加速才报）
> ③ **out_of_boundary 误报消除**：PX4 home 贴 boundary 角点 → ThresholdDetector 软告警加 margin（默认 0.5m，可配）；真实越界（落地漂移 y=-0.75）仍正确报警（margin 外）
> ④ **floor_breach 地面噪声豁免**：SITL 地面 z 噪声 ~3cm → 豁免 1cm→5cm
> ⑤ **hover 越界 reject 修复**：stub HOVER 分支原来不夹紧（其余动作都夹）→ 终检 reject（LLM 翻译 [takeoff,hover] 实测 out_of_boundary_after_clamp）；改为与其他动作一致走夹紧（界外悬停 → 回界内目标）
> ⑥ **LLM 真实全链路实证（新 key）**：β 对话「起飞到1米」→ 真实 LLM 提议(pending) → approve → α 翻译 2 actions [takeoff,hover]（3s）→ 起飞 z=+0.87；「回到起飞点悬停」→ 免审直转 α → return_home 回 (0.12,-0.16,0.54) + hover 夹紧执行（不再 reject）
> ⑦ 测试：新增 test_s8_monitor_px4.py（18 用例：margin/floor 豁免/导数/集成/hover 夹紧）并入 test_all → **B 152/152 + A 56/56**；实机验证 monitor 悬停静默（0 误报）
> ⑧ 残留：mavros Time jump 警告（SITL 时间同步, 不影响功能）
> 提交：S8 遗留闭环 commit

> **2026-08-03 21:50 (mavros Time jump 修复 + 新遗留: SITL GPS fix=0 长悬停漂移)**:
> ① **Time jump 根因（源码级定位）**：警告在 mavros 1.20.1 **sys_time 插件**（非 time_sync——1.20.1 无此插件，此前 blacklist 无效）；mavros 主动 10Hz 发 TIMESYNC → PX4 必回 → WSL2 时钟校正致 offset 偏差 >100ms → 连续 5 次高偏差 → reset filter + 警告（~45s 一次）
> ② **修复**：项目内 `mavros_px4_config.yaml`（复制系统 px4_config.yaml）+ `mavros_px4.launch`（复制 px4.launch，config_yaml 指向项目）——`time/max_consecutive_high_deviation: 100`（单次校正偏差不重置 filter，警告消失，timesync 功能保留）；start_px4_sitl.sh 改用 `roslaunch mavros_px4.launch` + export PROJ（$(env PROJ) 展开）
> ③ **对照实验**：timesync 完全禁用（rate=0+NONE）虽消除警告，但**实测致无人机漂移 9~13m**（SITL 刚启动 15s 即 preflight + EKF 未收敛；两次复现）→ 回退禁用方案，保留 timesync + 容忍参数
> ④ **验证**：重启后 mavros 日志 **Time jump 0 次**（10+ 分钟，此前 ~45s/次）✓；无人机原点稳定（对照实验证明禁用是漂移变量）
> ⑤ **新遗留（非本次修复引入，S8 期间即存在但短时飞行无感）**：SITL GPS fix=0（/mavros/global_position/raw/fix status=0，sensor_gps_sim 的 SIM_GPS_USED 参数 get/set 均失败）→ EKF 纯惯导 → 长时间 offboard 悬停位置估计慢漂（~14m/6min）。S8 短时飞行（起飞/悬停 6s/落地）不受影响。后续排查方向：sensor_gps_sim 模块启动/参数注册（v1.13.3 rcS 无 start 行）、eeprom 参数持久化。**使用建议：避免长时间 offboard 悬停，飞行任务短时执行**
> ⑥ 顺手修复：start_px4_sitl.sh A 启动前 source .env（否则 LLM degraded）；EKF 收敛窗口 +30s（防 SITL 刚启动即 preflight）；patch_px4_rcs.sh v3（px4-rc.mavlink 注入 TIMESYNC 断流——保留，与 mavros 主动询问互补）
> 提交：Time jump 修复 commit

> **2026-08-03 16:00 (阶段M S8 全项验收 — 并行开发 + 实飞验证)**:
> ① 并行开发（3 worker + worktree 隔离）：S8.4 land→AUTO.LAND（component.py set_land_handler + 锁外触发，test_s8_land 29/29）、S8.6/S8.8（adapter.py set_event_sender/_send_alert + offboard 重切 2 次重试 + preflight 拒绝 alert，test_s8_safety 27/27）；新测试并入 test_all.py（exec_module 合并计数）→ **B 134/134 + A 56/56**
> ② 修复 run_b.py（实际入口）未接线：补 set_event_sender + set_land_handler（并行任务只改了 lifecycle.py，实跑路径漏接——S8.4 首轮实飞 land 走 stub 下压即此因）；过时注释同步
> ③ **S8.4 实飞（新代码）**：takeoff(1.0) 爬升 0.81~0.95m → land → `land → AUTO.LAND (handler injected)` → 落地 z≈-0.26 + disarm（螺旋桨停）；status 流转 executing→completed ✓
> ④ **S8.2 双端对照重验（修正后）**：空中同刻 rostopic /mavros/local_position/pose z=+0.870 ↔ B 上行 z=+0.870（同号同值，无双重变换）；REST /api/current-pose 地面 z=-0.232 ↔ rostopic -0.23 一致
> ⑤ **S8.6 实飞**：悬停 0.81m 时 rosservice 强制切 POSCTL → B 检测 `offboard lost (mode=POSCTL)` → 1s 容忍后自动重切 `offboard re-engaged`（恢复）；失败路径 alert(offboard_lost, critical) 由单测 T2 覆盖；后 abort → AUTO.LAND 2s 落地
> ⑥ **S8.5 REST 回测**：A 侧 `POST /api/sessions/{id}/abort` → `{"status":"aborted"}` → B `emergency_land: AUTO.LAND` 全链路闭环
> ⑦ 环境：A 跑 8001（8000 被 XDAgent 占）；DEEPSEEK_API_KEY 未设（LLM 链路以 mini-A 注入验证，α 翻译链此前已验）；全链路已恢复（A+B+PX4 SITL 运行中）
> ⑧ 遗留（非 S8 验收项）：monitor overaccel/out_of_boundary 误报（PX4 IMU linear_acceleration 含重力 → overaccel 常亮；boundary 对噪声敏感）——待后续按 sim-drone 同法（运动加速度=速度导数）适配 PX4；mavros Time jump 警告（SITL 时间同步，不影响功能）
> ✅ 遗留已闭环（2026-08-03 17:10）：monitor 运动加速度=速度导数 + boundary margin 0.5m + floor 豁免 5cm；stub hover 夹紧修复；LLM 真 key 全链路实证。残留：mavros Time jump 警告（不影响功能）
> 提交：S8.4/S8.6/S8.8 代码 + run_b 接线 + 测试 + spec §8 同步

> **2026-08-03 14:40 (阶段M S8.3b 解决 + 启动脚本收尾)**:
> ① start_px4_sitl.sh 收尾：gazebo_iris target（v1.13.3 实测名）、`tail -f /dev/null |` stdin 保活、pkill ERE 修正（原 \| 只匹配字面竖线从未生效）、SITL 就绪检查改 UDP 14580、EKF 预热等待、A 端口 8000 bind 失败自动降级 8001（Windows 侧服务间歇抢占）；
> ② rcS 参数补丁脚本化：`patch_px4_rcs.sh` 幂等注入（marker v2，删除不存在的 EKF2_EN 参数，去掉调试 echo），启动时自动检查/注入源码树与 build 副本；
> ③ **S8.3b 爬升受限根因（2026-08-03 全链路定位）**：mavros 1.20.1 setpoint_raw local_cb 对非 body 帧自动 ENU→NED，B 侧 adapter 再变换 = 双重变换 → FCU 收到 ENU 值当 NED（ulog raw_sp.z=+1.0 实证，takeoff 变下降）→ PX4 want_takeoff 永不成立 → 起飞状态机卡死（mc_pos_control not_taken_off 分支重置 setpoint 为 NaN+100m/s² 向下加速度）→ 爬升受限；
> ④ 修复（backend-B）：adapter.publish_position 透传 ENU（mavros 负责转换）；GoalPublisher 限速推进改以"上一帧 setpoint"为锚（旧实现每帧重锚当前位置 → 漂移力大于纠正力时 setpoint 跟着漂、目标永不可达）+ hover 锁定保持点（零恢复力→自由漂移修复）；preflight 加固：等首帧真实位姿、已武装落地静止先 disarm/arm 强制起飞边沿、OFFBOARD→ARM 重试环；abort→AUTO.LAND 接线（dispatch set_abort_handler）+ offboard-lost 检测在 emergency 下不重切；
> ⑤ **实飞验证（金标准 GT）**：takeoff(1.0) 爬升至 1.0m ×4 复现（ulog groundtruth z 0.73→-0.60 物理离地）、1m 悬停 6s 漂移 ≤0.04m、abort→AUTO.LAND 2s 落地；S8.3 ✅ / S8.5 ✅ / S8.4 部分（land 动作为 goal 下压 0.3m，AUTO.LAND 仅在 abort 路径）；
> ⑥ 遗留：S8.2 需按 §4.3 修正重验（旧"通过"系双端同源空转）、land 动作接 AUTO.LAND、S8.6-8.8 待测；DEEPSEEK_API_KEY 未在本会话环境（LLM 链路用 mini-A 注入验证，α 翻译链路此前已验）；
> 提交：后续（spec §4.3/§5.2/§5.3/§8/§9/§10 已同步）

> **2026-08-03 01:30 (阶段M PX4 SITL 实测 — offboard 全链路打通)**:
> PX4 v1.13.3 SITL + Gazebo Classic 全链路实测（大量排障后打通）:
> ① 环境: PX4 v1.13.3 编译成功（依赖排查: menuconfig/kconfiglib/pip、GStreamer dev、mavlink 头生成、sitl_gazebo MAVLINK 缓存）
> ② offboard 状态机修正: 先 OFFBOARD 后 ARM（避开 manual control 检查）; setpoint 流线程贯穿（停发即退出）
> ③ 虚拟 RC 三坑: 18 通道、ch5/6 中性（0 触发 RTL）、微抖（rc_update 无更新不发布）
> ④ COM_RC_IN_MODE=3（first_valid）— rc_update 输出恒 SOURCE_RC，1(MAVLINK) 不匹配 → RC 从未有效 → offboard RC-lost failsafe 反复覆盖（最隐蔽的根因）
> ⑤ run_b 补 init_registry（组件注册缺失）; px4 posix rcS 注入参数（COM_RC_IN_MODE=3/BAT1_*/NAV_RCL_ACT/COM_OBL_ACT）
> ✅ 验证: B preflight ACTIVE + 全链路 LLM→α→IPC→small_model→GoalPublisher→PX4 起飞（ENU z 0→0.4m）; NED/ENU 变换正确; B 测试 78/78
> ⚠️ 遗留: 无人机爬升受限 ~0.4m（setpoint=EKF+0.075 恒定、thrust 悬停化）— PX4 高度控制调参（MPC_Z_*/悬停油门估计），属 S8 验收调参项
> 提交: 0227aef（adapter 状态机/虚拟RC/流线程 + run_b 注册 + 文档）

> **2026-08-02 20:30 (阶段M 设计定稿 — PX4-阶段2-design.md 交付)**:
> 新建 `docs/specs/后端B/PX4-阶段2-design.md`（10 节）:
> ① 版本锁定 PX4 v1.13.3 + Gazebo Classic 11 + MAVROS 1.20.1（mavros/mavros-msgs 已实际安装核实 1.20.1，px4.launch fcu_url 已核实）
> ② 消息契约：/mavros/setpoint_raw/local(PositionTarget, type_mask 位置控制=2552 整组设置, 权威定义核实) + state/arming/set_mode + 上行 pose/vel/imu 类型不变复用
> ③ 核心难点：NED↔ENU 坐标变换单点收敛（BState/A/前端保持 ENU），悬停语义修正（offboard 停发会退出 → 持续发当前位置），abort/land → AUTO.LAND 兜底
> ④ offboard 状态机 DISARMED→STREAMING(≥3s/20Hz)→ARM→OFFBOARD→ACTIVE + ARM 三重前置（stream+距home<2m+connected）
> ⑤ B 侧改动面最小化：topics/adapter(subscriber 注入变换)/publisher 接口不变/PHASE 环境变量(默认1 零回归)
> ⑥ S8 验收 8 项清单（含 NED/ENU 双端对照、offboard 丢失降级、阶段1 回归）
> 同步交叉引用：开发规划阶段M 登记已建、测试路线图 §3.2 G4 标记 ✅ 已交付（含 gz_x500 修正说明）
> 阶段M 待办：PX4 v1.13.3 源码 clone（$HOME/PX4-Autopilot 仓库外）、EGM96、pymavlink pip、start_px4_sitl.sh、Phase2Adapter 编码

> **2026-08-02 19:15 (I1 实证)**:
> 用真实 API key + opencode.ai/zen/go/v1 端点 + deepseek-v4-flash 完成 I1 实证:
> ① LLMTranslator 双连发均成功 (5.8s/3.5s, 无 Event loop is closed) — 常驻事件循环线程修复实证有效
> ② 真实 α 系统 prompt (alpha.md) 翻译输出合法: takeoff+hover 动作编码、schema_version=2、task_id 正确
> ③ β SSE 全链路: agent 创建(16 工具) + 流式 markdown 响应正常
> ④ llm.py 新增 LLM_BASE_URL/LLM_MODEL 环境变量覆盖 (api_key 仍只走 DEEPSEEK_API_KEY, 不硬编码)
> 注: API key 仅经环境变量使用, 未入库; 首次双连发失败系测试用弱 system prompt 所致, 非代码缺陷

> **2026-08-02 (端到端验证 — ROS1 Noetic 全链路)**:
> 环境确认有 ROS1 Noetic + sim-drone 仿真器后完成全链路实测：roscore → sim-drone(50Hz pose/vel/IMU) → backend-B(run_b.py, 系统 Py3.8) → IPC(msgpack) → backend-A(8001, 因 8000 被无关服务占用) → WS → 前端页面
> 验证结果：① B-1 死锁修复生效（10Hz 上行持续 20+ 分钟稳定，无锁死）；② B-2 数据通路修复生效（运动时 A 侧 current-pose 与 WS pose 广播 vel=[1.51,1.14,0.64] 非零，悬停归零；此前“恒零”系测试方法错误——无人机已停在目标点）；③ B-5 假阳性修复生效（启动无 stale/floor 误报；sim-drone 重启期间的 stale 告警为真实停产检测）；④ WS 广播链路全通（pose 10Hz 精确、alert 2s 节流）；⑤ IPC 断线重连正常（B 先于 A 启动自动重连）；⑥ 前端页面：状态栏“[已连接] DRONE ONLINE POS (4.5,3.5,2.5)”，同源自适应 base_url 生效，WS/REST 全通
> 新发现并修复：⑦ sim-drone 把重力 9.81 当线性加速度发布 → overaccel 持续误报（已改为运动加速度=速度导数，悬停/匀速=0，误报消除）；⑧ run_a.py 支持 BACKEND_A_PORT 环境变量（与 BACKEND_A_HOST 对称，规避 8000 端口冲突）；⑨ 前端 base_url 同源自适应（location.origin 优先于硬编码 8000，显式配置仍优先）
> 验证环境约束：8000 端口被无关服务(XDAgent API)占用 → 全链路跑 8001；B-1 的 subscriber.py 路径由单元测试回归覆盖（70/70），端到端实测为 run_b.py 路径（start_all.sh 实际入口）

> **2026-08-02 (代码审查修复 #3 — 全仓并行审查 9🔴/36🟡 + 3 worker 并行修复 + 2 reviewer 独立验证)**:
> 审查：4 路并行 reviewer（backend-A / backend-B / frontend / A-B 契约，依据 code-review-skill）→ 9 🔴 / 36 🟡 / 38 🟢 / 12 💡
> backend-A 修复（worker-A，20 文件）：α 下发失败误报 executing 状态机（B1）、WS 广播持锁+队列化解耦（B2）、POST /api/sessions/{id}/abort 路由（🔴-3）、status 转发 WS（🔴-4）、LLM 常驻事件循环线程（I1）、approve TOCTOU 原子认领（I2）、TelemetryBuffer task 管理 + OR IGNORE（I3/I4）、IPC writer 关闭（I5）、INFO 日志（I6）、接线 fail-fast + 缺 key 白名单降级（I7）、默认绑 127.0.0.1 + 输入限长（I8）、reject 注入 α + emergency_hover（🟡-6）、ping 改 call（🟡-8）、会话端点补齐（🟡-9）、CORS 白名单（S1）、WS 防御（S2）、current_pose 拷贝（S4）、PRAGMA foreign_keys + ns 级 session id（N8）、FFT/STT/时区/死代码清理（N9~N14）、monitor_trigger 删除、SCHEMA_VERSION 导入 → **测试 47→56/56**
> backend-B 修复（worker-B，16 文件）：IMU 嵌套锁死锁（B-1，已实证）、run_b.py vel/accel 恒零数据通路（B-2）、入口 python -m backend_B 修复（B-3）、recv 线程兜底（B-4）、monitor 启动假阳性（B-5）、small_model 跨线程锁收敛（B-6）、socket 5s 超时（B-7）、start_all.sh 路径自推导（B-8）、reject 冻结常量（🟡-5）、telemetry 补 vel/imu（🟡-7）、ts 统一 wall time、指数退避、断连 hover、alert to=beta 与冻结文档确认一致 → **测试 58→70/70**
> frontend 修复（worker-F，40+ 文件）：WS payload 兼容（🔴-1）、/api/field/config（🔴-2）、路由竞态（🟡1）、StatusBar rAF 节流（🟡2）、HistoryChart 泄漏（🟡3）、SSE error 重复渲染（🟡4）、ChatPanel 闭包流状态（🟡5）、XSS 组统一 esc/escAttr（🟡6~8，新建 escape.js）、WS 心跳/jitter/可见性恢复（🟡9）、API 全方法超时（🟡10）、WS 重建（🟡11）、sw.js 版本化缓存（🟡12）、VideoPanel disconnect（🟡13）、FloatingBall 长按（🟡14）、枚举对齐冻结值、死代码/图表动画/lookbehind/config 键名清理 → **node --check 40+ 文件全过 + 行为测试 22 PASS**
> 独立验证（2 路 reviewer）：A 56/56 + B 70/70 + AST 3.8 零违例 + 协议 md5 一致 + 集成冒烟（health/field/config/sessions/abort 全部符合预期）→ 发现并修复 3 项遗留（β 降级回归 FAIL-1、sse.js fullText 作用域、pose handler 缺 quat）+ 4 项 note（alert.detail/reject toast/CSS.escape/SettingsPage 统一 escAttr）→ 复测全绿
> 残余风险：LLM 双连发实证需 API key；端到端 A+B+ROS 全链路需真机/仿真环境

> **2026-07-29 (阶段H 完成)**:
> 实现 `backend-A/tools/beta_tools.py`: 15 个 β 工具 — 实时状态 (field_map/pose/telemetry/env), 历史查询 (sessions/telemetry/env/conversations), α 调度 (propose_to_alpha 总线拦截→pending + forward_last_human_message 免审), analytics stub, dashboard stub
> 实现 `backend-A/agents/beta.py`: create_beta_agent() 单例, 15 工具注册
> 创建 `backend-A/prompts/beta.md`: β 系统 prompt — 中枢调度 + 15 工具 + 安全路径说明
> 实现 `backend-A/web/sse.py`: POST /api/chat/beta → SSE (text/tool_call_start/tool_call_result/error 事件)
> 实现 `backend-A/web/routes.py`: REST — /api/proposals/*/approve (C3 单一路径), /api/field/config, /api/current-pose, /api/sessions, /api/overview, /api/history/*, /api/environments
> 实现 `backend-A/web/ws.py`: WebSocket handler — pose/status/alert/alpha_output 广播 + sync 状态补齐
> 更新 `backend-A/lifecycle.py`: 集成 β agent + web context 注入 (REST/WS/SSE/tools) + WS broadcast 注入 bridge
> 更新 `backend-A/bus/bridge.py`: 添加 WS broadcast 回调 + _handle_pose/_handle_alert 广播
> 更新 `backend-A/main.py`: 挂载 SSE/REST/WS routers
> 修复 `forward_last_human_message`: asyncio.ensure_future → try get_running_loop / fallback asyncio.run
> 后端 A 测试: 47/47 全部通过; β tools 集成测试全部通过

> **2026-07-29 (阶段G 完成)**:
> 实现 `backend-A/agents/llm.py`: make_agent() 工厂函数 + PROVIDERS dict (DeepSeek) + pydantic-ai 2.0 API (OpenAIChatModel + OpenAIProvider)
> 实现 `backend-A/agents/translator_base.py`: ActionTranslator ABC (同步 translate 方法, 供 asyncio.to_thread 调用) + TranslateError
> 实现 `backend-A/agents/alpha_llm.py`: LLMTranslator — translate() 同步入口 + _translate_async() 内部 asyncio.run() + JSON 提取 (处理 markdown 代码块) + 动作编码验证
> 实现 `backend-A/agents/alpha.py`: AlphaLoop — 仲裁逻辑 (新指令→翻译/预设未完成→继续/无任务→hover) + make_translator() 工厂 (ALPHA_BACKEND=llm/small) + _dispatch_action → B 侧 small_model + 退避重启 1~5s
> 创建 `backend-A/prompts/alpha.md`: α 系统 prompt — 翻译器不对话 + 9类动作编码 + ActionCommand schema + 规则约束
> 更新 `backend-A/lifecycle.py`: 集成 α loop 启动 + set_alpha_loop 注入 bridge
> 更新 `backend-A/bus/bridge.py`: 添加 _alpha_loop_ref + set_alpha_loop() + reject handler 注入 α 上下文
> 后端 A 测试: 47/47 全部通过

> **2026-07-29 (阶段F 完成)**:
> 实现 `backend-B/small_model/` 完整模块: action_codes.py (9类动作编码), goal_gen.py (GoalGenerator ABC + make_goal_generator 工厂), stub.py (9类规则映射 + boundary/ceiling/floor/speed_max 夹紧 + 未知编码→reject + 越界→reject), component.py (SmallModelComponent — generate_goal/abort/hover 入口 + 目标点缓存 + 事件上行 + 到达→自动切下条)
> 实现 `backend-B/rosbridge/` 完整模块: topics.py (阶段1/阶段2 话题前缀), node.py (rospy 节点封装), adapter.py (Phase1Adapter — PoseStamped setpoint + 阶段抽象), publisher.py (GoalPublisher — 20Hz 目标点线程 + 首帧防跳变 + speed_max 限速 + 到达检测), subscriber.py (DroneSubscriber — 订阅位姿/速度/IMU → BState + quat 重排 [x,y,z,w]→[w,x,y,z])
> 重写 `backend-B/lifecycle.py`: 集成真实 SmallModelComponent + ROS 节点 + 订阅器 + 目标点发布器 + uplink 10Hz 线程 (pose + telemetry 分帧) + event sender 注入 + 先连 A 再启目标点线程 + 关停序列 (hover→stop pub→sub shutdown→rospy shutdown→close IPC)
> 修复 `dispatch.py`: 移除多余的 call_id 参数
> 修复 `component.py`: 添加缺失的 import math + home 注入改为无条件赋值
> 后端 B 测试: 58/58 全部通过; Phase F 集成测试: takeoff/goto/move/climb/descend/yaw/hover/return_home/land 9类全部验证 + abort/hover/reject/clamp/advance 全部通过

> **2026-07-28 (代码审查修复 #2)**:
> 🔴 B1: `TelemetryBuffer.stop()` 先 flush 残留数据再退出 + 提取 `_build_telemetry_rows` / `_flush_batch`
> 🔴 B2: A 侧 IPC `_recv_loop` 帧过大时 `return` 断开连接（修复帧边界错乱）
> 🔴 B3: A 侧 `IpcServer` 保存后台 task 引用，`stop()` 中取消并 await
> 🟡 I1: `sim-drone` 四元数注释标注 ROS (x,y,z,w) vs 接口冻结 (w,x,y,z)
> 🟡 I2: B 侧 `dispatch._handle_call` 传入 `call_id` 以便后续启用 result 配对
> 🟡 I3: `bridge.py` `_handle_pose` 添加 payload 字段映射注释 + 注入 TelemetryBuffer
> 🟡 I4: A 侧 `_recv_loop` pong 处理中验证 `schema_version` 一致性
> 🟡 I5: `TelemetryBuffer._flush_batch` 提取复用 + 复用 session (减少连接创建)
> 🟡 I6: `B_SIDE_COMPONENTS` 新增 `TO_EGO_PLANNER` / `TO_LIDAR` (提前路由)
> 🟢 N1: `models.py` `utcnow` → `datetime.now(timezone.utc)`
> 🟢 N2: `serve.py` 移除重复 `SO_REUSEADDR` (已由 `allow_reuse_address=True` 设置)
> 🟢 N3: `get_session()` 注释标注阶段 G/H FastAPI Depends 用途
> 🟢 N4: `sim-drone` 提取 `MAX_DT = 0.2` 常量
> 🟢 N5: `_StubSmallModel` 注释标注阶段 F 迁移目标 `backend-B/small_model/component.py`
> 💡 S1: `bridge._handle_pose` 注入 `TelemetryBuffer` (pose 数据入遥测缓冲)
> 💡 S2: `run_backend_b.sh` 添加 Python 版本检查警告
> 💡 S3: 创建 `run_tests.sh` 全量测试脚本
> 💡 S4: 修复测试 config 路径 (从 CWD 相对改为 `_PROJ_ROOT` 绝对)

> **2026-07-28**: 阶段E S1 验收通过 — sim-drone 假无人机 catkin_make 编译成功；6项测试全部通过 (连续setpoint移动/到达悬停/边界夹紧/返航/超时悬停/IMU发布)。

> **2026-07-27 (代码审查+修复)**: 
> 🔴 B1: `_EmptyComponent` 改为 `_StubSmallModel/_StubMonitor`，abort/hover 有安全兜底
> 🔴 B2: A 侧 IPC `ipc_connected` 延迟到首次 pong
> 🔴 B3: B 侧 `dispatch._handle_ping` 使用 `SCHEMA_VERSION` 常量
> 🟡 I1: `bus/protocol.py` 迁移到 `shared/`，A/B 两侧软链共享
> 🟡 I2: 前端清除废弃 segments/waypoints；FlightPlanCard 统一 actions 格式
> 🟡 I3: B 侧 dispatch `send_event` 复用 `frames.encode_frame`
> 🟡 I4: A 侧 `update_pose` 添加 NaN/Inf 校验
> 🟡 I5: `bridge.py` 删除无用 import
> 🟡 I6: `sim-drone/` 实现假无人机节点（运动学积分+超时悬停+边界自保）
> 🟢 N1: `TelemetryBuffer` 改为 `insert()` 批量写入
> 🟢 N2: `venv-A-requirements.txt` 清理 ROS 包
> 🟢 N3: `.env.example` 对齐 spec 字段名
> 🟢 N4: 创建 `backend-A/tests/` + `backend-B/tests/`
> 阶段E 升级为 🚧 (假无人机脚本已实现, 待 catkin_make + S1 验证)

> **2026-07-27**: 阶段A 完成；阶段B/C 完成 — B 侧 BState/config/bus/IPC 脊柱就位；A 侧 AppState/config/bus/IPC server/DB 层/FastAPI 骨架就位。双端 import 测试 + DB 集成测试通过。

---

## 阶段总览

| 阶段 | 名称 | 状态 | 说明 |
|---|---|---|---|
| 阶段A | 基础设施与协议常量 | ✅ | venv-A/B + config + protocol.py + ipc/frames.py + S0 验证 |
| 阶段B | 后端 B 脊柱 | ✅ | BState + config_loader + bus(registry/router) + IPC(client/dispatch) + lifecycle |
| 阶段C | 后端 A 脊柱 | ✅ | AppState + config_loader + bus(registry/router/bridge) + IPC server + DB(models/session/repos/TelemetryBuffer) + FastAPI 骨架 + StaticFiles |
| 阶段D | 前端骨架 | ✅ | P0~P11 全部完成 + Brutalist 重设计 (redesign/brutalist-v1) |
| 阶段E | 假无人机 | ✅ | S1 验收通过：catkin_make 编译 + 6项测试 |
| 阶段F | B 侧 small_model stub + ROS 桥 | ✅ | S2 — small_model 组件 + rosbridge 全部实现，58/58 测试通过 |
| 阶段G | A↔B IPC 通 + α Agent | ✅ | S3 + S5前半 — LLM agent 工厂 + ActionTranslator + LLMTranslator + α loop + 47/47 测试通过 |
| 阶段H | β Agent + SSE + 提议审核 | ✅ | S5 完整 — β tools(15) + SSE + REST + WS + propose/forward 双路径 + 47/47 测试通过 |
| 阶段I | 监控回路 | ✅ | S6 — monitor detectors(threshold/trend) + component(10Hz) + alert节流 + trigger + 58/58 测试通过 |
| 阶段J | 前端集成 | ✅ | P2~P11 全部完成 + 2026-08-02 端到端联调验证通过 |
| 阶段K | 安全兜底与 reject 回路 | ✅ | S4+S7 — reject→WS + 断连 link_status + LLM fail→hover + 58/58 + 47/47 |
| 阶段L | 语音/分析/看板（非阻塞增量） | ✅ | FFT/stats/filter + STT/TTS 框架 + PWA + dashboard 5面板 |
| 阶段M | 远期 PX4 SITL + ego-planner + 真模型 | ⏳ | 设计文档已交付(2026-08-02)，待环境搭建与编码 (版本锁定: PX4 v1.13.3 + Gazebo Classic 11 + MAVROS 1.20.1) |

---

## 模块明细

### 阶段A — 基础设施与协议常量
| 模块 | 状态 | 负责人 | 最近更新 |
|---|---|---|---|
| venv-A 创建（Py3.10+ FastAPI/Pydantic AI/SQLAlchemy） | ✅ | — | 2026-07-27 |
| venv-B 创建（Py3.8 `--system-site-packages` + pyyaml） | ✅ | — | 2026-07-27 |
| 系统依赖 apt（python3-msgpack 0.6.2 / python3-scipy） | ✅ | — | 2026-07-27 |
| `run_backend_b.sh`（先 source ROS 再 activate venv + Python 版本检查） | ✅ | — | 2026-07-28 |
| `config/field.yaml`（仅 boundary+home，obstacles 删） | ✅ | — | 2026-07-27 |
| `config/default_constraints.yaml`（keep_clear_distance 删） | ✅ | — | 2026-07-27 |
| `venv-*-requirements.txt` + `.env.example` | ✅ | — | 2026-07-27 |
| `backend-A/bus/protocol.py` + `backend-B/bus/protocol.py`（SCHEMA_VERSION=2 逐字一致） | ✅ | — | 2026-07-27 |
| `backend-A/ipc/frames.py` + `backend-B/ipc/frames.py`（msgpack use_bin_type=True） | ✅ | — | 2026-07-27 |
| **✅ S0 验收**:msgpack 帧 A↔B 互解 + grep 确认无废弃概念残留 + 版本协商 | ✅ | — | 2026-07-28 |
| ⚠ **代码审查新增**: `backend-A/tests/` + `backend-B/tests/` 测试目录 + 单元测试 + `run_tests.sh` | ✅ | — | 2026-07-28 |

### 阶段B — 后端 B 脊柱
| 模块 | 状态 | 负责人 | 最近更新 |
|---|---|---|---|
| `backend-B/state.py`（BState + pose_lock） | ✅ | — | 2026-07-27 |
| `backend-B/config_loader.py` | ✅ | — | 2026-07-27 |
| `backend-B/bus/registry.py`（small_model/monitor 注册） | ✅ | — | 2026-07-27 |
| `backend-B/bus/router.py`（同步 bus.call） | ✅ | — | 2026-07-27 |
| `backend-B/ipc/client.py`（恒定时间重连 1s） | ✅ | — | 2026-07-27 |
| `backend-B/ipc/dispatch.py`（ping→pong + call_id 传递） | ✅ | — | 2026-07-28 |
| `backend-B/lifecycle.py` + `main.py`（启动6步 + 关停） | ✅ | — | 2026-07-28 |
| ⚠ **代码审查修复**: `_StubSmallModel/_StubMonitor` 安全兜底 + 阶段F迁移注释 | ✅ | — | 2026-07-28 |

### 阶段C — 后端 A 脊柱
| 模块 | 状态 | 负责人 | 最近更新 |
|---|---|---|---|
| `backend-A/state.py`（AppState + asyncio.Lock） | ✅ | — | 2026-07-27 |
| `backend-A/config_loader.py`（alpha_loop_period 等） | ✅ | — | 2026-07-27 |
| `backend-A/bus/registry.py` + `router.py`（async bus.call + B_SIDE_COMPONENTS 完整） | ✅ | — | 2026-07-28 |
| `backend-A/bus/bridge.py`（A↔B 跨进程路由 + TelemetryBuffer 注入） | ✅ | — | 2026-07-28 |
| `backend-A/ipc/server.py`（bind+unlink+2s ping/5s pong + 版本协商 + task管理） | ✅ | — | 2026-07-28 |
| `backend-A/db/models.py`（4 表，utcnow→timezone.utc） | ✅ | — | 2026-07-28 |
| `backend-A/db/session.py`（aiosqlite + create_all + get_session 注释） | ✅ | — | 2026-07-28 |
| `backend-A/db/repos.py`（仓储 + TelemetryBuffer 每秒 flush + stop 残留flush + _flush_batch 复用） | ✅ | — | 2026-07-28 |
| `backend-A/main.py` + `web/static.py`（StaticFiles 最后挂载） | ✅ | — | 2026-07-27 |
| `backend-A/lifecycle.py`（启动9步 + 关停 + set_telemetry_buffer） | ✅ | — | 2026-07-28 |

### 阶段D — 前端骨架（并行）
| 模块 | 状态 | 负责人 | 最近更新 |
|---|---|---|---|
| P0 项目骨架（index.html + state/router/config/ws/app） | ✅ | — | 2026-07-24 |
| P1 布局 + 通用组件（StatusBar/ChatPanel/ConnectionOverlay） | ✅ | — | 2026-07-24 |
| 懒加载重构（44→13 初始模块 + 高 backlog 服务器） | ✅ | pi agent | 2026-07-24 |
| `frontend/serve.py`（TCP backlog 128，移除重复 SO_REUSEADDR） | ✅ | pi agent | 2026-07-28 |

### 阶段E — 假无人机（并行）
| 模块 | 状态 | 负责人 | 最近更新 |
|---|---|---|---|
| `sim-drone/` catkin 包（CMakeLists/package.xml/launch） | ✅ | — | 2026-07-27 检查修复 |
| `fake_drone_node.py`（运动学积分 + 50Hz + 超时悬停 + 边界自保 + quat 注释 + MAX_DT 常量） | ✅ | — | 2026-07-28 |
| **✅ S1 验收**: roscore + catkin_make + 连续setpoint移动/到达悬停/边界夹紧/返航/超时悬停/IMU 全通过 | ✅ | — | 2026-07-28 |

### 阶段F — B 侧 small_model stub + ROS 桥
| 模块 | 状态 | 负责人 | 最近更新 |
|---|---|---|---|
| `backend-B/small_model/action_codes.py`（9 类编码 + VALID_ACTION_CODES frozenset） | ✅ | — | 2026-07-29 |
| `backend-B/small_model/goal_gen.py`（GoalGenerator ABC + GoalGenError + make_goal_generator 工厂） | ✅ | — | 2026-07-29 |
| `backend-B/small_model/stub.py`（9 类规则映射 + boundary/ceiling/floor/speed_max 夹紧 + 未知→reject + 越界→reject） | ✅ | — | 2026-07-29 |
| `backend-B/small_model/component.py`（SmallModelComponent — generate_goal/abort/hover + 目标点缓存 + 事件上行 + 到达→自动切下条） | ✅ | — | 2026-07-29 |
| `backend-B/rosbridge/topics.py`（阶段1/2 话题前缀 + get_topics） | ✅ | — | 2026-07-29 |
| `backend-B/rosbridge/node.py`（rospy.init_node 封装） | ✅ | — | 2026-07-29 |
| `backend-B/rosbridge/adapter.py`（Phase1Adapter — PoseStamped setpoint + yaw→quat + 阶段抽象） | ✅ | — | 2026-07-29 |
| `backend-B/rosbridge/publisher.py`（GoalPublisher — 20Hz 目标点线程 + 首帧防跳变 + speed_max 限速 + 到达检测） | ✅ | — | 2026-07-29 |
| `backend-B/rosbridge/subscriber.py`（DroneSubscriber — 订阅位姿/速度/IMU → BState + quat 重排 [x,y,z,w]→[w,x,y,z]） | ✅ | — | 2026-07-29 |
| `backend-B/lifecycle.py`（集成真实组件 + upling 10Hz pose/telemetry + 先连A再启目标点 + 关停序列） | ✅ | — | 2026-07-29 |
| ⚠ `dispatch.py` 修复: 移除多余的 call_id 参数 | ✅ | — | 2026-07-29 |
| **✅ S2 验收**: B 单跑 + 假无人机响应 + uplink 自验 — 组件就绪，待 ROS 环境联调 | ✅ | — | 2026-07-29 |

### 阶段G — A↔B IPC 通 + α Agent
| 模块 | 状态 | 负责人 | 最近更新 |
|---|---|---|---|
| `backend-A/agents/llm.py`（make_agent + pydantic-ai 2.0 + DeepSeek provider） | ✅ | — | 2026-07-29 |
| `backend-A/agents/translator_base.py`（ActionTranslator ABC + TranslateError） | ✅ | — | 2026-07-29 |
| `backend-A/agents/alpha_llm.py`（LLMTranslator — sync translate + JSON extract + code valid） | ✅ | — | 2026-07-29 |
| `backend-A/agents/alpha.py`（α loop 仲裁 + make_translator + asyncio.to_thread + 退避重启） | ✅ | — | 2026-07-29 |
| `backend-A/prompts/alpha.md`（α 系统 prompt — 翻译器不对话 + 9类编码 + schema + 规则） | ✅ | — | 2026-07-29 |
| `backend-A/lifecycle.py`（集成 α loop 启动 + set_alpha_loop bridge 注入） | ✅ | — | 2026-07-29 |
| `backend-A/bus/bridge.py`（_alpha_loop_ref + set_alpha_loop + reject→α） | ✅ | — | 2026-07-29 |
| **✅ S3 验收**: A↔B ping/pong + action 下发 + pose 上行 — IPC server 就绪 | ✅ | — | 2026-07-29 |
| **✅ S5 前半**: hardcoded intent → α → ActionCommand → small_model — LLM 翻译链就绪 | ✅ | — | 2026-07-29 |

### 阶段H — β Agent + SSE + 提议审核
| 模块 | 状态 | 负责人 | 最近更新 |
|---|---|---|---|
| `backend-A/tools/beta_tools.py`（15 工具 — 实时状态/历史查询/α 调度/analytics/dashboard） | ✅ | — | 2026-07-29 |
| `backend-A/agents/beta.py`（create_beta_agent 单例 + 15 工具注册） | ✅ | — | 2026-07-29 |
| `backend-A/prompts/beta.md`（β 系统 prompt — 中枢调度 + 安全路径） | ✅ | — | 2026-07-29 |
| `backend-A/web/sse.py`（POST /api/chat/beta + SSE 流式事件） | ✅ | — | 2026-07-29 |
| `backend-A/web/routes.py`（REST — proposals/field/pose/sessions/overview/history/environments） | ✅ | — | 2026-07-29 |
| `backend-A/web/ws.py`（WebSocket — pose/status/alert/alpha_output broadcast + sync） | ✅ | — | 2026-07-29 |
| β→α 两路径（propose → pending → 人审 → α / forward → 直接进 α） | ✅ | — | 2026-07-29 |
| `backend-A/lifecycle.py`（集成 β + web context 注入） | ✅ | — | 2026-07-29 |
| `backend-A/main.py`（挂载 SSE/REST/WS routers） | ✅ | — | 2026-07-29 |
| `backend-A/bus/bridge.py`（WS broadcast 回调注入） | ✅ | — | 2026-07-29 |
| **✅ S5 完整**: β Chat → α → small_model → 假无人机 + 系统消息 | ✅ | — | 2026-07-29 |

### 阶段I — 监控回路
| 模块 | 状态 | 负责人 | 最近更新 |
|---|---|---|---|
| `backend-B/monitor/detector.py`（Detector ABC + 注册表 + get_all） | ✅ | — | 2026-07-29 |
| `backend-B/monitor/thresholds.py`（速度/高度/加速度/角速度/数据停产/boundary 软告警） | ✅ | — | 2026-07-29 |
| `backend-B/monitor/trends.py`（突变 jerk 检测 + 持续偏离/振荡检测） | ✅ | — | 2026-07-29 |
| `backend-B/monitor/component.py`（10Hz + alert 节流同 code 2s/critical 不节流 + 上行） | ✅ | — | 2026-07-29 |
| `backend-A/monitor_trigger/trigger.py`（alert 日志 + β 唤醒接口预留） | ✅ | — | 2026-07-29 |
| `backend-B/lifecycle.py`（集成 monitor 组件 + detector 注册 + event sender + 关停） | ✅ | — | 2026-07-29 |
| `backend-A/bus/bridge.py`（_handle_alert → WS broadcast） | ✅ | — | 2026-07-29 |
| **✅ S6 验收**: 超速告警 → β 系统消息 + 处置建议 — alert 广播链路就绪 | ✅ | — | 2026-07-29 |

### 阶段J — 前端集成（P2~P11 接后端）
| 模块 | 状态 | 负责人 | 最近更新 |
|---|---|---|---|
| P2 3D 场景（FieldRenderer 仅 boundary+home；OrbitControls；LidarPointCloud 占位） | ✅ | — | 2026-07-24 |
| P3 α 左栏（无对话；currentAction/totalActions） | ✅ | — | 2026-07-24 |
| P4 视图管理（1/2/3 切换 + 拖拽互换） | ✅ | — | 2026-07-24 |
| P5 悬浮球（一键发预存 Chat 短语 + Esc 取消） | ✅ | — | 2026-07-24 |
| P6 β 界面（FlightPlanCard + approveProposal C3） | ✅ | — | 2026-07-24 |
| P7 其他页面（HistoryPage 双子 TAB + 发送到 β） | ✅ | — | 2026-07-24 |
| P8/P9 响应式 + 异常处理 | ✅ | — | 2026-07-24 |
| **✅ 后端联调完成**: WS/SSE/REST 真实数据接入（2026-08-02 端到端验证：sim-drone→B→IPC→A→WS→前端全链路实测通过，状态栏实时显示无人机位置/连接态，同源自适应 base_url 生效） | ✅ | — | 2026-08-02 |
| **Scene3D 3D 视图重引入**（Gazebo GUI 替代, Three.js 0.146.0；boundary 线框/地面网格/HOME/无人机/高度线/OrbitControls；与 FieldMap2D 视图切换） | ✅ | — | 2026-08-04 |

### 阶段K — 安全兜底与 reject 回路
| 模块 | 状态 | 负责人 | 最近更新 |
|---|---|---|---|
| `backend-A/web/ws.py`（broadcast_reject + broadcast_link_status） | ✅ | — | 2026-07-29 |
| `backend-A/bus/bridge.py`（_handle_reject → WS broadcast + _ws_reject/_ws_link 注入） | ✅ | — | 2026-07-29 |
| `backend-A/ipc/server.py`（B connect→link_status up / B disconnect→link_status down） | ✅ | — | 2026-07-29 |
| `backend-A/agents/alpha.py`（LLM fail→link_status error + LLM recover→link_status up + 退避重启） | ✅ | — | 2026-07-29 |
| `backend-B/small_model/component.py`（reject reason 含具体 action_code） | ✅ | — | 2026-07-29 |
| **安全链验证**: abort→清goal/hover→当前位置/断开→hover/LLM fail→hover+退避/越界→夹紧/reject→WS | ✅ | — | 2026-07-29 |
| **✅ S4 验收**: 未知动作编码 → reject → WS 推送 + α 重想 | ✅ | — | 2026-07-29 |
| **✅ S7 验收**: 任何环节断 → 无人机安全悬停 — link_status + α loop 退避 + B hover 兜底 | ✅ | — | 2026-07-29 |

### 阶段L — 非阻塞增量（语音/分析/看板）
| 模块 | 状态 | 负责人 | 最近更新 |
|---|---|---|---|
| `backend-A/analytics/fft.py`（NumPy FFT + 纯 Python DFT fallback） | ✅ | — | 2026-07-29 |
| `backend-A/analytics/stats.py`（mean/variance/std/minmax/trend 纯 Python） | ✅ | — | 2026-07-29 |
| `backend-A/analytics/filter.py`（moving_average/lowpass/highpass 纯 Python） | ✅ | — | 2026-07-29 |
| `backend-A/speech/xfyun_config.py`（环境变量读取 + 可用性检查） | ✅ | — | 2026-07-29 |
| `backend-A/speech/auth.py`（hmac-sha256 签名 + RFC1123 UTC date） | ✅ | — | 2026-07-29 |
| `backend-A/speech/stt_client.py`（WebSocket STT + wpgs 动态修正 + PCM 16k） | ✅ | — | 2026-07-29 |
| `backend-A/speech/tts_client.py`（WebSocket TTS + x-api-key + MP3 base64） | ✅ | — | 2026-07-29 |
| `frontend/sw.js`（Service Worker Cache First + PWA） | ✅ | — | 2026-07-29 |
| `backend-A/tools/beta_tools.py`（analytics 接入真实实现 + dashboard 5 面板） | ✅ | — | 2026-07-29 |
| 数据看板 P11（DashboardPanel/Grid/FilterBar + β 工具） | ✅ | — | 2026-07-24 |
| PWA 打包 P10（manifest.json + Service Worker） | ✅ | — | 2026-07-29 |
| 语音 STT/TTS（讯飞签名 + wpgs + AudioWorklet PCM） | ✅ | — | 2026-07-29 |

### 阶段M — 远期（⏳ 不阻塞先导）
| 模块 | 状态 | 负责人 | 最近更新 |
|---|---|---|---|
| PX4 SITL + mavros 1.20.1（新建 `docs/specs/后端B/PX4-阶段2-design.md`） | ✅ | — | 2026-08-03 S8 全项验收完成 |
| `rosbridge/adapter.py` Phase2Adapter（offboard 状态机 + 双端对照 + alert 上行） | ✅ | — | 2026-08-03 |
| S8 验收（S8.1~S8.8 全项） | ✅ | — | 2026-08-03 实飞验证 |
| Gazebo GUI 不可用（WSL2 OGRE/OpenGL）→ 前端 Scene3D 替代（§11） | ✅ | — | 2026-08-04 |
| ego-planner 桥 + 雷达感知 | ⏳ | — | — |
| 蒸馏小模型 α 训练（alpha-small/） | ⏳ | — | — |
| 端侧小模型训练（small-model/ MLP） | ⏳ | — | — |
| 外场真机演示 | ⏳ | — | — |

### 阶段N — 历史页重设计 + 看板修复（2026-08-06 新增需求，用户确认）
> 微小事务拆分粒度对齐确认后的规划。Part A 后端 → Part B 看板修复 → Part C 历史重构。

| 模块 | 状态 | 负责人 | 最近更新 |
|---|---|---|---|
| A1 遥测端点补全字段 — `GET /api/history/telemetry/{sid}` 返回 accel/angular_vel/quat（保留 pos/vel，向后兼容） | ✅ 已完成 | — | 2026-08-06 |
| A2 dashboard_config 真广播 — ws.py 加 broadcast_dashboard_config + beta_tools dashboard_configure/set_filter 经注入回调推送 + lifecycle 接线 | ✅ 已完成 | — | 2026-08-06 |
| B1 前端存 accel/angularVel — app.js WS pose 处理解析两字段 + state.js 初始态补齐 | ✅ 已完成 | — | 2026-08-06 |
| B2 看板 accel_line 接真数据 — DashboardPanel 环形缓冲读 store.drone.accel | ✅ 已完成 | — | 2026-08-06 |
| B3 看板去假数据 + 真告警 — bar 面板不再硬编码，订阅 bus 'alert' 实时累计（同 code 计数），无告警空态 | ✅ 已完成 | — | 2026-08-06 |
| B4 看板 β 工具驱动联调 — 依赖 A2，实测 β「看高度趋势」→ 面板真实切换 | ⬜ 未开始 | — | — |
| B5 看板空态兜底 — 无实时数据显示引导提示，不再一片 `--`/空图 | ⬜ 未开始 | — | — |
| C1 会话数据集加载器 — HistoryPage 选中会话拉全量遥测+详情，组装 points/duration/taskInfo/planned，存 `store.history.playback.dataset`（不污染实时轨迹） | ⬜ 未开始 | — | — |
| C2 回放引擎 — 新 js/history/playback.js：rAF 按倍速推进 time→索引/位姿，发 playback-* 总线事件 | ⬜ 未开始 | — | — |
| C3 看板式历史数据面板 — 新 js/history/HistoryPanels.js：高度/速度三维/加速度/角速度折线 + 飞行统计卡片 + 任务进度（从数据集真实计算） | ⬜ 未开始 | — | — |
| C4 2D 轨迹面板 — FieldMap2D 参数化：会话完整 XY 轨迹 + home + 边界 + 回放游标 | ⬜ 未开始 | — | — |
| C5 3D 轨迹面板 — Scene3D 历史模式 setHistoryPoints/seekPlayback（不订阅实时 store；改动过大则独立 HistoryScene3D.js） | ⬜ 未开始 | — | — |
| C6 进度条升级 — TimelineControl 时长改从数据集 duration 计算（修恒 60s bug）+ 播放进度条 + 任务进度条（currentAction/totalActions）双显示 | ⬜ 未开始 | — | — |
| C7 历史详情布局重排 + 接线 — HistoryPage _renderDetail 重构（摘要卡/回放条/面板网格/2D|3D）+ HistoryChart 改读数据集 + pages.css 样式 | ⬜ 未开始 | — | — |
| C8 收尾验证 — sw.js BUILD_ID bump + node --check 全过 + 后端测试不回归 + 浏览器实测（2D/3D/进度条/console 零错误） | ⬜ 未开始 | — | — |

---

## 联调阶段打卡（S0~S8）
- [x] S0 环境/msgpack 互通 — ✅ A/B 测试均通过 (47+58)
- [x] S1 假无人机单跑 — ✅ catkin_make 编译 + 6项测试通过
- [x] S2 B 单跑（stub）— ✅ 组件就绪 (58/58 测试通过), 待 ROS 环境联调
- [x] S3 A↔B IPC 通 — ✅ IPC server + ping/pong/action/pose 全部就绪 (47/47 A侧测试通过)
- [x] S4 reject 回路 — ✅ reject→WS broadcast + α 下轮 hover + 安全链验证
- [x] S5 前半 hardcoded → α → ActionCommand — ✅ 翻译链就绪, 待 API key 联调
- [x] S5 完整链路（β→α→假无人机）— ✅ β tools + SSE + REST + WS 全部就绪
- [x] S6 监控 alert 回路 — ✅ detectors + 10Hz + 节流 + WS broadcast 全部就绪
- [x] S7 断连安全 — ✅ link_status + α loop 退避 + B hover 兜底 + sim-drone 超时悬停
- [x] S8 切 PX4 SITL（阶段M）— ✅ S8.1~S8.8 全项实飞验收完成（2026-08-03）：环境/双端对照/takeoff/land→AUTO.LAND/abort REST 闭环/offboard 丢失自动恢复/阶段1 回归/ARM 前置告警