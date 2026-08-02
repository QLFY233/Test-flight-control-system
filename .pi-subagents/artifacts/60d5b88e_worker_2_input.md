# Task for worker

[Read from: /home/QLFY233/Test-flight-control-system/context.md, /home/QLFY233/Test-flight-control-system/plan.md]

You are a delegated subagent running from a fork of the parent session. Treat the inherited conversation as reference-only context, not a live thread to continue. Do not continue or answer prior messages as if they are waiting for a reply. Your sole job is to execute the task below and return a focused result for that task using your tools.

Task:
修复 frontend（vanilla JS SPA）全部审查问题。先读报告 /tmp/code-review/frontend-report.md 和 /tmp/code-review/contract-report.md 中涉及前端的部分。项目根 /home/QLFY233/Test-flight-control-system。

【文件边界】只允许改 frontend/**（含 js/、index.html、serve.py、sw.js、config 文件）；禁止改 backend-A/**、backend-B/**、shared/protocol.py。注意后端与前端 spec 保持对齐，前端改代码适配。

【必须修复】
🔴-1：js/ws.js:150-166 _dispatch — 后端广播是顶层字段 {type, pos, ...} 无 payload 键，改为 `handler(data.payload !== undefined ? data.payload : data, data)` 兼容双层；随后检查 app.js:177-209 各 handler 的字段名（后端 pose 用 pos/quat、link_status 用 link/state 等，见 🟡-2）并对齐。
🔴-2：js/api.js:152 — getFieldConfig 路径改 '/api/field/config'（后端路由名）。
🔴-3 配合：后端将补 POST /api/sessions/{id}/abort；前端同时修复 🟡-1 枚举使 ABORT 按钮能显示。
🟡 1：js/router.js:40-46 — 路由竞态：记录 pendingHash，finally 中对比 location.hash 与 currentHash 不一致则递归 _onChange。
🟡 2：js/app.js:138-146 — StatusBar/BottomBar 订阅风暴：改为 rAF 节流合并同帧通知，或组件增量更新；移除重复订阅（L114 与 L140 都订阅 connection）。
🟡 3：js/charts/HistoryChart.js:38-46 — bus.on 返回值当 unsubscribe：保存具名回调引用再 off；空处理器删除。
🟡 4：js/sse.js:97-100 + js/components/ChatPanel.js:163-175 — SSE error 事件后跳过 onComplete（errored 标记）；修复后错误只渲染一条消息。
🟡 5：js/components/ChatPanel.js — 并发流式竞态：流状态收敛到 sendMessage 闭包局部变量，各回调只操作自己的流元素。
🟡 6~8（XSS 组）：js/components/ChatMessage.js:72-73 toolName 转义；js/components/SessionCard.js:44 title 属性转义（新增 escAttr 处理引号）；js/pages/AlphaPage.js:47-65、js/pages/HistoryPage.js:185-188、js/components/FlightPlanCard.js:85、js/components/DashboardPanel.js:48-50,169-170、js/components/DashboardGrid.js:82-85、js/pages/OverviewPage.js:205、js/pages/BetaPage.js:142,160 全部统一转义。建议按 💡1 新建 frontend/js/escape.js 提供 esc/escAttr 并替换 4 套近似实现。
🟡 9：js/ws.js — 加 ping 心跳（15-30s，N 次无响应主动 close）、退避加 ±20% 抖动、visibilitychange 恢复重连（app.js:159 no-op 监听器接入或删除）。
🟡 10：js/api.js — post/patch/delete 也走 AbortController 超时（抽公共 _fetchWithTimeout），AbortError 给用户提示。
🟡 11：js/pages/SettingsPage.js:248-249 — 保存后端 URL 后重建/重连 WsManager 或提示需刷新生效。
🟡 12：frontend/sw.js — 版本化缓存名（如拼接日期/构建号），dev 环境跳过 SW 注册或改 Stale-While-Revalidate。
🟡 13：js/components/VideoPanel.js — unmount 中 ro.disconnect()；renderFrame 补 img.onerror。
🟡 14：js/components/FloatingBall.js — 长按编辑死功能：实例化 ShortcutEditor 或在长按后抑制 click 展开误触。
🟢 1~9 全部：OverviewPage 死代码 _resetHideTimer 删除；AlphaPage #floating-ball-container 死分支清理；app.js visibilitychange no-op 处理；app.js 重复 connection.ws 赋值统一；ChatMessage lookbehind 正则改兼容写法；AltitudeChart/VelocityChart 高频 setOption 关动画或节流；SettingsPage alert/confirm 改 toast + parseFloat NaN 校验；sse.js abort 空消息处理；config-default.json 键名对齐。
💡 1~4：统一 escape.js（见上）；state.js 注释文档化；index.html echarts CDN 若无法本地化则给图表组件加 typeof echarts 守卫与降级提示（检查是否有本地 echarts 可用）；serve.py 默认绑 127.0.0.1 + 参数显式开放。
契约 🟢：api.js 死代码 getTelemetry/getConversations/getCurrentPose 按后端真实路由修正（/api/history/telemetry/{sid}、/api/history/conversations/{sid}、/api/current-pose）或删除；getProposals 去掉多余 session_id 参数；link_status 字段按后端 link/state 映射到 connection.backendA/backendB/drone/llm（🟡-2）。

【自测】node --check 所有改动的 js 文件；python3 -m py_compile frontend/serve.py；grep 确认无遗漏的未转义插值点；如有 python3 起 http.server 做一次页面加载冒烟（可选）。
【输出】写入 /tmp/code-review/fix-frontend.md：改动文件清单、修复项对照表（编号→状态 done/skip+原因→验证方式）、自测结果、残余风险。禁止使用 WebSearch。

---
Update progress at: /home/QLFY233/Test-flight-control-system/.pi-subagents/artifacts/progress/60d5b88e/progress.md

---
**Output:**
Write your findings to exactly this path: /tmp/code-review/fix-frontend.md
This path is authoritative for this run.
Ignore any other output filename or output path mentioned elsewhere, including output destinations in the base agent prompt, system prompt, or task instructions.

## Acceptance Contract
Acceptance level: checked
Completion is not accepted from prose alone. End with a structured acceptance report.

Criteria:
- criterion-1: Implement the requested change without widening scope

Required evidence: changed-files, tests-added, commands-run, residual-risks, no-staged-files

Finish with a fenced JSON block tagged `acceptance-report` in this shape:
Use empty arrays when no items apply; array fields contain strings unless object entries are shown.
`criteriaSatisfied[].status` must be exactly one of: satisfied, not-satisfied, not-applicable.
`commandsRun[].result` must be exactly one of: passed, failed, not-run.
`manualNotes` and `notes` are optional strings; an empty string means no note and does not satisfy `manual-notes` evidence.
```acceptance-report
{
  "criteriaSatisfied": [
    {
      "id": "criterion-1",
      "status": "satisfied",
      "evidence": "specific proof"
    }
  ],
  "changedFiles": [
    "src/file.ts"
  ],
  "testsAddedOrUpdated": [
    "test/file.test.ts"
  ],
  "commandsRun": [
    {
      "command": "command",
      "result": "passed",
      "summary": "short result"
    }
  ],
  "validationOutput": [
    "validation output or concise summary"
  ],
  "residualRisks": [
    "none"
  ],
  "noStagedFiles": true,
  "diffSummary": "short description of the diff",
  "reviewFindings": [
    "blocker: file.ts:12 - issue found, or no blockers"
  ],
  "manualNotes": "anything else the parent should know"
}
```