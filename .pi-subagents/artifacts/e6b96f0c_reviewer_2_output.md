# Frontend 全面代码审查报告

- 审查对象：`frontend/`（vanilla JS SPA，5903 行：js/ 11 个核心模块 + 6 pages + 20 components + 4 charts + serve.py + sw.js）
- 审查依据：任务指定的安全/重连/状态管理/清理/错误处理/竞态/代码质量 7 个维度
- 注：仓库根目录无 `plan.md` / `progress.md`（任务头部指定路径不存在），本次按任务书自身规格审查
- 无前端自动化测试（`*.test.js`/`*.spec.js` 均不存在）

---

## 🔴 blocking（0 项）

未发现必须阻塞合入的问题。最接近严重级别的问题（XSS 类、路由竞态、渲染风暴）均归入 🟡，理由：本系统为单机/内网部署、无不可信远端用户输入，服务端数据源受信任；但下列 🟡 中 XSS 一组属于"纵深防御必改"项，建议在下一轮修复中优先处理。

---

## 🟡 important（14 项）

### 1. 路由竞态：快速切换页面时导航被吞掉，页面与 URL 失同步（可能卡死）
`js/router.js:40-46,63-99`
- `_onChange()` 用 `this._changing` 布尔锁，动态 `import()` 期间（首次加载 chunk，可能几十~几百 ms）发生的第二次 hashchange 被直接丢弃（L40-41 `if (this._changing) return;`）。
- 后果：hash 已变为 `#/beta`，但页面停在 Alpha，`currentHash='#/alpha'`；之后点击 Beta 标签不会再次触发 hashchange（hash 未变），用户被"卡"在错误页面。
- 修复建议：改为记录 `pendingHash`，`finally` 中若 `window.location.hash !== this.currentHash` 则递归调用 `_onChange()`；或每次进入时先对比当前 hash 再决定是否跳过。

### 2. StatusBar/BottomBar 订阅风暴：每条遥测消息触发 5 次全量 innerHTML 重建
`js/app.js:138-146`
- `store.subscribe('drone', ...)` 会对 `drone.position/velocity/attitude/timestamp/connected` 5 个路径各触发一次（state.js `_notify` 前缀匹配，batch 只去重同路径），即**每条 pose 消息重建 5 次 StatusBar**；pose 频率假设 10–30 Hz → 每秒 50–150 次整条状态栏 DOM 重建。`flight`/`trajectory` 订阅同理重建 BottomBar。
- 另有重复订阅：L114 与 L140 都订阅 `connection`；`__event:open/close` 与 `connection` 消息也重复写 `connection.ws`（app.js:168-171）。
- 修复建议：状态栏改为"订阅后增量更新文本节点"或在 `requestAnimationFrame` 内节流（合并同帧多次通知）；StatusBar/BottomBar 改为实例复用（`sb.update()`），而不是每次 `new ...mount()`。

### 3. HistoryChart 事件监听器泄漏：bus.on 返回值被当作 unsubscribe 使用
`js/charts/HistoryChart.js:38-39,45-46`
- `EventBus.on()` 不返回任何值（event-bus.js:17-24 无 return），而 HistoryChart 把 `bus.on('playback-seek', ...)` 的结果存为 `_timeUnsub`，unmount 时执行 `bus.off('playback-seek', undefined)` —— 是 no-op。
- 后果：每次打开历史详情挂载一次 HistoryChart，就泄漏 2 个 bus 处理器（`playback-seek` + `playback-state-changed`），闭包持有整个 chart 实例，永久无法 GC。反复查看不同会话详情 → 内存持续增长。
- 修复建议：保存具名回调引用：`this._onSeek = (t) => this._updateTimeCursor(t); bus.on('playback-seek', this._onSeek); ... bus.off('playback-seek', this._onSeek);`。`playback-state-changed` 的空处理器直接删除。

### 4. SSE error 事件后重复渲染：onError 与 onComplete 都会追加一条 agent 消息
`js/sse.js:97-100` + `js/components/ChatPanel.js:163-175`
- `sendMessage` 收到 SSE `error` 事件时调用 `onError`（ChatPanel 替换占位元素并 `_addMessage('agent', ...)`）；随后流结束**无条件**调用 `onComplete(fullText)`（sse.js 无 error 标记），ChatPanel 的 onComplete 因 `streamingMessageEl` 已为 null 而再次 `appendChild(finalEl)` 并再次 `_addMessage`。
- 后果：服务端报错时聊天区出现两条消息（错误气泡 + 残缺正文气泡），store 也重复记录。
- 修复建议：sse.js 用 `let errored=false` 标记，error 事件后跳过 `onComplete`；或在 ChatPanel 的 onError 里置位并在 onComplete 中短路。

### 5. ChatPanel 并发流式请求竞态：共享 streamingMessageEl/streamingContent
`js/components/ChatPanel.js:18-19,129-130,135-137,153-171`
- 两条消息连续发送时，第二次 `_sendMessage` 覆盖 `this.streamingMessageEl/streamingContent`，第一次流的 `onMessage/onComplete` 会操作错误的占位元素并互相覆盖内容。
- 修复建议：流状态收敛到局部变量（sendMessage 内的闭包），完成回调里只操作自己创建的 `streamEl`；或将输入框在流式期间禁用。

### 6. XSS 组 A — ChatMessage toolName 未转义直插 innerHTML
`js/components/ChatMessage.js:72-73,86-87`
- `<span>${toolName || 'Tool Call'}</span>`：toolName 来自 SSE `tool_call_start` 的 `parsed.name`（服务端/LLM 数据），未 escape。
- 修复：`${ChatMessage._escapeHtml(toolName || 'Tool Call')}`（content 已先行 escape，仅 toolName/toolArgs 路径遗漏）。

### 7. XSS 组 B — SessionCard title 属性引号逃逸
`js/components/SessionCard.js:44`
- `title="${FlightPlanCard_esc(this.session.task_summary || '')}"`：`FlightPlanCard_esc` 基于 `div.textContent → innerHTML`，**不转义 `"` 和 `'`**，在属性上下文可逃逸（`task_summary` 含 `" onmouseover=...` 即可注入）。task_summary 为 LLM 生成的摘要，含引号完全现实。
- 修复：新增同时转义 `"`/`'` 的 `escapeAttr()` 助手（参照 SettingsPage._escAttr），或在 title 中用 `title="${escAttr(...)}"`。

### 8. XSS 组 C — 页面内服务端数据插值未转义
- `js/pages/AlphaPage.js:47-65`：`${env.location}`、`${flight.taskTitle}`、`${a.code}`、`${JSON.stringify(flight.currentActionParams)}` 直接拼进 innerHTML（location 为用户在设置页可输入的自由文本）。
- `js/pages/HistoryPage.js:185-188`：`${session.task_title}`、`${session.task_summary}` 未转义。
- `js/components/FlightPlanCard.js:85`：`value` 字段 `${value + ' ' + units}` 未转义（其余字段均 `_esc`，仅此遗漏）。
- `js/components/DashboardPanel.js:48-50,169-170`：`spec.title`、`spec.value`、`spec.unit` 未转义（来自 WS `dashboard_config`）。
- `js/components/DashboardGrid.js:82-85`：`panel_id` 未转义插入 `id`/`data-panel-id` 属性（WS 服务端数据）。
- `js/pages/OverviewPage.js:205`、`js/pages/BetaPage.js:142,160`：`e.message`（含服务端 error detail）拼入 innerHTML。
- 修复建议：提供统一的 `esc()`（文本）与 `escAttr()`（属性）助手并全量替换上述插值点；错误信息一律用 `textContent` 写入。

### 9. WsManager 无心跳/无可见性恢复
`js/ws.js`（全文件，重连逻辑见 211-231）
- 指数退避实现正确（1s→2s→…→30s cap，open 后重置），但：① 无 ping/pong 心跳 —— 网络静默中断（睡眠/断网）时连接可能长时间停留在 OPEN 假活状态，无任何数据触发检测；② 无随机抖动（jitter），多客户端同时重连会同步冲击服务端；③ 无 `visibilitychange` 恢复逻辑（app.js:159 的监听是 no-op）。
- 修复建议：每 15–30s `send({type:'ping'})`，N 次无响应则主动 `close()` 触发重连；退避加 ±20% 抖动；页面恢复可见时检查 `getStatus()` 并重连。

### 10. api.js POST/PATCH/DELETE 无超时
`js/api.js:34-58`
- 仅 `get` 有 AbortController 超时（默认 10s）；`post/patch/delete`（含 `abortSession`、`approveProposal` 等关键操作）无超时，服务端挂起时 Promise 永久 pending —— BottomBar 的 abort 按钮会永远停在"中断中..."（BottomBar.js:49-52）。
- 修复：抽公共 `_fetchWithTimeout(method, ...)`，全部方法走超时；并对 AbortError 给用户可读提示。

### 11. 设置页修改 backend URL 后 WS 仍连旧地址
`js/pages/SettingsPage.js:248-249` + `js/app.js:88-89`
- 保存设置只 `apiManager.setBaseUrl()`，`WsManager` 的 URL 在 init 时已固定，且未触发重连。改后端地址后 REST 走新地址、WS 走旧地址，行为分裂且无任何提示。
- 修复：保存后重建/重连 WsManager（`window.__app.wsManager.disconnect()` 后 `new WsManager(newUrl).connect()` 并重新注册 handlers），或提示"需刷新页面生效"。

### 12. sw.js Cache First 缓存永不失效（开发与上线双坑）
`frontend/sw.js:4,59-69`
- `CACHE_NAME='flight-control-v1'` 硬编码；fetch 拦截对静态资源 Cache First 且回源成功后写缓存。代码更新后（dev 迭代或上线）浏览器继续用旧缓存，且 sw.js 字节不变不会触发 SW 更新 —— 用户看到的一直是旧版应用，直到手动清缓存。
- 修复：版本号纳入构建（`CACHE_NAME = 'flight-control-v' + BUILD_ID`）；dev 环境跳过 SW 注册；或改用 Stale-While-Revalidate + 缓存头校验。

### 13. VideoPanel ResizeObserver 未 disconnect
`js/components/VideoPanel.js:24-27,39-45`
- `mount` 创建 `ResizeObserver` 观察 container，`unmount` 只清空引用，未 `ro.disconnect()`；observer 仍持有已脱离文档的 container，持续触发回调。同时 `renderFrame` 无 `img.onerror` 处理（坏帧静默失败）。
- 修复：`this._ro` 保存引用并在 unmount 中 disconnect；补 `img.onerror`。

### 14. FloatingBall 长按编辑模式是死功能 + 长按会误触发展开
`js/components/FloatingBall.js:51-57` + `js/components/ShortcutEditor.js:24-33`
- `ShortcutEditor` 在整个前端**从未被实例化**（grep 无 `new ShortcutEditor`），`open-shortcut-editor` 事件无人监听 → 长按 600ms 进入编辑模式完全无效；且释放时 click 事件照常触发 `_expand()`，表现为"长按后球展开"的误触。
- 修复：在 app.js 启动时实例化 ShortcutEditor，或在长按触发后抑制随后的 click（记录 `longPressed` 标志并在 click 处理器短路）。

---

## 🟢 nit（9 项）

1. **`js/pages/OverviewPage.js:154-157`**：`_resetHideTimer` 定义后从未调用（注释已说明不用自动隐藏），死代码，删除。
2. **`js/pages/AlphaPage.js:107-113`**：`#floating-ball-container` 元素从未渲染，`floatingBall` 分支恒为 null；AlphaPage 又 import 了 FloatingBall，死分支。移除或接入 app.js 的 `#fb` 实例。
3. **`js/app.js:159`**：`visibilitychange` no-op 监听器，删除（或按 #9 实现真逻辑）。
4. **`js/app.js:167-171`**：`__event:open/close` 与 `connection` 消息对 `connection.ws` 重复赋值（一个断连触发 2 次通知 → 2 次 StatusBar 重建 + overlay 判断），统一走一条路径。
5. **`js/components/ChatMessage.js:108`**：正则 lookbehind `(?<!\*)` 在 Safari < 16.4 直接语法错误导致整个模块无法加载；改用无 lookbehind 写法（如先处理 `**bold**` 再处理单 `*`，用字符类排除）。
6. **`js/charts/AltitudeChart.js:33-47` / `VelocityChart.js:32-40`**：每次 pose 更新整表 setOption（含 300 点 xAxis 数组重建）+ `animationDuration:300`，高频下动画队列堆积；建议 `animation:false` 或节流（≥100ms）。
7. **`js/pages/SettingsPage.js:256-280`**：多处 `alert()`/`confirm()` 阻塞弹窗，且 `_saveSettings` 在非 environment tab 时经 `''` 兜底逻辑勉强正确，但 `parseFloat` 可产出 `NaN`（如清空输入），`JSON.stringify` 后变 `null` 落库；建议输入校验 + 用 toast（系统已有 bus 'toast'）替代 alert。
8. **`js/sse.js:97-99`**：Abort 时 `onComplete('')` 会渲染一条空 agent 消息；建议单独 `onAbort` 回调或在 abort 时跳过 onComplete。
9. **`frontend/config-default.json`**：键名与代码不一致（`voice.auto_tts` vs SettingsPage 读 `vc.autoTts`；`environment.wind_speed` vs store `windSpeed`；`backend.request_timeout` 未被 api.js 使用）。默认值目前"碰巧"正确，属于隐性约定。

---

## 💡 suggestion（4 项）

1. **统一转义与渲染策略**：全仓 58 处 innerHTML，转义规则散落（`ChatMessage._escapeHtml`、`FlightPlanCard._esc`、`SessionCard.FlightPlanCard_esc`、`SettingsPage._escAttr` 4 套近似实现）。抽 `src/lib/escape.js` 提供 `esc`/`escAttr`，删除重复实现。
2. **`js/state.js`**：Store 实现本身正确（前缀通知、batch 去重、unsubscribe 返回值齐全），但建议给 `subscribe` 文档注明"通知值可能是前缀路径的标量值"；另外 `store.getState()` 返回内部引用，调试便利但易误改，可考虑只读代理。
3. **`frontend/index.html:20`**：echarts 走 jsdelivr CDN + Google Fonts `@import`；本环境存在代理/证书问题（见 CLAUDE.md），CDN 失败时 `AltitudeChart` 等直接 `echarts.init` 会抛 ReferenceError（仅 DashboardPanel 有 `typeof echarts` 守卫）。建议本地化 echarts 或统一守卫 + 降级提示。
4. **`frontend/serve.py:26-32`**：开发服务器默认绑定 `0.0.0.0` 且 `Access-Control-Allow-Origin: *`；同网段任意网页可跨域读取前端静态文件。开发可用，但建议默认 `127.0.0.1` + 启动参数显式开放，并在 README 注明。

---

## 🎉 praise

- **Store/EventBus 基础设计扎实**：`state.js` 的 dot-path + 前缀订阅 + batch 去重 + 可返回 unsubscribe，`event-bus.js` 的 handler 异常隔离（try/catch 单点保护），是本次审查中质量最高的模块；页面级 `bus.on/off`（AlphaPage/BetaPage）配对完整，ViewPanel/图表类组件的 `_unsubscribe`/`dispose` 清理模式正确。
- **WsManager 退避实现正确**：指数退避 + 上限 + open 重置 + intentionalClose 语义，`_scheduleReconnect` 防重入（clearTimeout 前置）都处理得当。
- **ChatMessage._simpleMarkdown 先 escape 后渲染**：markdown 管道整体是 XSS 安全的（除 #6 的 toolName 遗漏），表格/代码块处理有意识。
- **Serve.py 的 backlog 修复**（128，默认 5 会 TCP RST）有明确问题驱动，注释到位。
- **无 3D/旧协议残留**：`TrajectorySpec/solver/waypoints` 等废弃概念按 CLAUDE.md 约定已清理（`obstacles` 仅留兼容空数组），代码与 `schema_version=2` 一致。

---

## 总体结论：**Comment**（建议修复后合入）

无阻塞问题，但有 2 项必须尽快处理的实质缺陷（#1 路由竞态卡死、#3 HistoryChart 监听器泄漏）和 1 组系统性改进（#6–#8 XSS 转义统一），以及 1 个性能隐患（#2 渲染风暴）。

### 最重要的前 5 个问题
1. **`js/router.js:40-46`** — 快速切换页面时导航被吞，页面/URL 失同步且无法恢复（点击同 hash 不触发事件）。
2. **`js/charts/HistoryChart.js:38-46`** — bus.on 返回值误当 unsubscribe，每次查看历史详情泄漏 2 个处理器（含 chart 实例闭包）。
3. **`js/app.js:140-146`** — pose 高频下 StatusBar 每秒 50–150 次全量 innerHTML 重建。
4. **`js/components/ChatMessage.js:72-73` / `js/components/SessionCard.js:44`** — 服务端数据未转义（含属性引号逃逸）XSS 隐患，需统一 esc/escAttr 修复全组。
5. **`js/sse.js:97-100` + `ChatPanel.js:163-175`** — SSE error 事件导致重复消息渲染 + 并发流共享状态竞态。