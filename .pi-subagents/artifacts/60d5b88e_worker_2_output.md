# Frontend 修复报告（worker 实施）

- 任务：修复 frontend（vanilla JS SPA）全部审查问题（frontend-report.md + contract-report.md 前端部分）
- 边界：仅修改 `frontend/**`；未触碰 backend-A/**、backend-B/**、shared/protocol.py（后端与 spec 对齐，前端改代码适配）
- 并行说明：backend-A / backend-B / start_all.sh 等由其他并行 worker 负责

---

## 修复项对照表

| 编号 | 问题 | 状态 | 改动文件 | 验证方式 |
|---|---|---|---|---|
| 🔴-1 | WS 载荷结构不匹配（全部实时数据被丢弃） | ✅ done | js/ws.js `_dispatch`：`payload ?? data` 兼容双层/顶层 | node 行为测试 PASS（type + wildcard handler 均收到顶层对象） |
| 🔴-2 | getFieldConfig 调 /api/field 404 | ✅ done | js/api.js → `/api/field/config` | grep 确认唯一调用点 |
| 🔴-3(前端侧) | abort 按钮永不显示（枚举错位） | ✅ done | state.js 枚举注释、BottomBar showAbort=`executing` | grep 'running'/'paused' 清除 |
| 🟡1 | 路由竞态导航被吞（可能卡死） | ✅ done | js/router.js finally 对比 hash 递归补跑 | node --check |
| 🟡2 | StatusBar 每秒 50–150 次 innerHTML 重建 | ✅ done | app.js：实例复用 + rAF 节流 + 4 订阅收敛 2+去重 | 代码审查确认 |
| 🟡3 | HistoryChart 监听器泄漏（bus.on 返回值误当 unsubscribe） | ✅ done | HistoryChart.js 具名回调 `_onSeek` + 删除空 handler | 代码审查确认 |
| 🟡4 | SSE error 后重复渲染两条消息 | ✅ done | sse.js `errored` 标记跳过 onComplete；ChatPanel 双保险 | 代码审查确认 |
| 🟡5 | ChatPanel 并发流共享状态竞态 | ✅ done | ChatPanel 流状态收敛到 sendMessage 闭包局部变量 | 代码审查确认 |
| 🟡6 | ChatMessage toolName 未转义 | ✅ done | ChatMessage.js `esc(toolName)` | node 行为测试（esc xss PASS） |
| 🟡7 | SessionCard title 属性引号逃逸 | ✅ done | SessionCard.js `escAttr()` | node 行为测试（quote breakout PASS） |
| 🟡8 | XSS 组（页面内服务端数据插值） | ✅ done | AlphaPage/BetaPage/HistoryPage/OverviewPage/FlightPlanCard/DashboardPanel/DashboardGrid/BottomBar/StatusBar/FloatingBall 全量 esc/escAttr | grep 复查 + 行为测试 |
| 🟡9 | WsManager 无心跳/抖动/可见性恢复 | ✅ done | ws.js 心跳（25s/静默 75s 判假活）+ ±20% jitter；app.js visibilitychange 主动重连 | node 行为测试（构造） |
| 🟡10 | api.js POST/PATCH/DELETE 无超时 | ✅ done | api.js `_fetchWithTimeout` 全方法 + `isTimeoutError` + 读 config.request_timeout | 代码审查确认 |
| 🟡11 | 设置页改后端 URL 后 WS 连旧地址 | ✅ done | SettingsPage emit `backend-url-changed`；app.js 重建 WsManager + 重注册 handlers + toast | 代码审查确认 |
| 🟡12 | sw.js Cache First 永不失效 | ✅ done | BUILD_ID 版本化缓存名 + Stale-While-Revalidate + escape.js 入预缓存 | node --check |
| 🟡13 | VideoPanel ResizeObserver 未 disconnect / 坏帧静默 | ✅ done | `this._ro.disconnect()` + `img.onerror` 回退无信号 | 代码审查确认 |
| 🟡14 | FloatingBall 长按死功能 + 误触发展开 | ✅ done | 长按置 `_longPressed` 抑制 click；app.js 常驻实例化 ShortcutEditor（激活编辑功能） | 代码审查确认 |
| 🟢1 | OverviewPage _resetHideTimer 死代码 | ✅ done | 删除（注释同步） | grep |
| 🟢2 | AlphaPage #floating-ball-container 死分支 | ✅ done | 删除分支 + FloatingBall import | node --check |
| 🟢3 | app.js visibilitychange no-op | ✅ done | 替换为真逻辑（见 🟡9） | — |
| 🟢4 | connection.ws 重复赋值 | ✅ done | 删除 `__event:open/close` 双写，单一 connection 消息路径 | 代码审查确认 |
| 🟢5 | ChatMessage lookbehind 语法错误（Safari<16.4） | ✅ done | 无 lookbehind 写法（bold 先转 `<strong>` 后单星号匹配） | node --check + 行为测试 |
| 🟢6 | 图表高频 setOption 动画堆积 | ✅ done | AltitudeChart/VelocityChart `animation:false` | node --check |
| 🟢7 | SettingsPage alert 阻塞 + parseFloat NaN | ✅ done | alert→toast；`toNum` Number.isFinite 校验回退 | 代码审查确认 |
| 🟢8 | sse.js abort 渲染空消息 | ✅ done | `onAbort` 回调替代 `onComplete('')`（ChatPanel 移除占位） | 代码审查确认 |
| 🟢9 | config-default.json 键名不一致 | ✅ done | `autoTts/sttEnabled/ttsEnabled/windSpeed/windDirection` 对齐代码 | json 校验 |
| 💡1 | 统一转义实现 | ✅ done | 新建 js/escape.js（esc/escAttr），11 文件接入，删除 4 套近似实现 | 行为测试 |
| 💡2 | state.js 文档化 | ✅ done | subscribe 前缀语义注释 + flight.status 冻结枚举注释 | — |
| 💡3 | echarts CDN 失败崩溃 | ✅ done | AltitudeChart/VelocityChart/HistoryChart/FieldMap2D 加 `typeof echarts` 守卫 + 降级提示；index.html 备用 CDN 回退（无本地 echarts 可用） | node --check |
| 💡4 | serve.py 默认 0.0.0.0 | ✅ done | 默认 `127.0.0.1`，显式参数开放（用法注释） | py_compile |
| 契约🟢 | api.js 死代码路径错误 | ✅ done | getTelemetry→`/api/history/telemetry/{sid}`、getConversations→`/api/history/conversations/{sid}`、getCurrentPose→`/api/current-pose`；getProposals 去掉 session_id | 代码审查确认 |
| 契约🟡-1/2 | 前端字段对齐后端（pos/vel/quat、flightStatus、link/state、alpha_output action/goal/remaining_actions） | ✅ done | app.js registerWsHandlers 全面重写 | 对照 backend-A/web/ws.py 逐字段核对 |

---

## 自测结果

1. `node --check` 25 个改动 js + sw.js：**全部通过**
2. `python3 -m py_compile serve.py`：**通过**
3. `config-default.json` JSON 合法（json.load + json.tool）：**通过**
4. 模块图解析：89 条 import 语句全部解析成功，**无缺失模块**
5. node + DOM stub 行为测试：
   - `esc('<img onerror=...>')` → `&lt;img onerror=...&gt;` ✅
   - `escAttr('a" onmouseover="alert(1)')` → 引号被转义，无法逃逸 ✅
   - `escAttr("it's")` → 单引号转义 ✅
   - ws `_dispatch` 顶层消息（无 payload 键）→ type + wildcard handler 均收到顶层对象 ✅
   - ws 内部 `{type:'connection', payload}` → handler 收到 payload ✅
6. http.server 冒烟：index.html / js/app.js / js/escape.js / config-default.json 均 200 ✅
7. grep 残留检查：`_escapeHtml`/`FlightPlanCard_esc`/`streamingMessageEl`/`_resetHideTimer`/`_timeUnsub`/`_playbackUnsub` 无残留（仅注释提及）✅

## 残余风险

1. **端到端联调未做**：本 worker 无浏览器工具；后端侧修复（abort 路由、status 转发、telemetry 补字段）由并行 worker 负责，需测试 subagent 起服务后联调验证全链路。
2. **心跳探测**：后端不回应应用层 ping；ws.js 仅在「曾收到数据后静默 75s」判定假活并主动断开，纯空闲连接（从未收到数据）不会误杀——该折中避免健康空闲连接被反复重连。
3. **ShortcutEditor 已激活**：modal 依赖 components.css 的 `.overlay`/`.modal`（已确认存在），但未做视觉验证；若样式不理想可回退为仅抑制长按误触。
4. **echarts 备用 CDN（unpkg）**回退逻辑未做真实网络验证（本环境代理限制）。
5. **status 枚举**：BottomBar 仅对 `executing` 显示 ABORT（冻结枚举）；若后端后续新增状态值需同步扩展。