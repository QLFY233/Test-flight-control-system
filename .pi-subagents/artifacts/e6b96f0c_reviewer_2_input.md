# Task for reviewer

[Read from: /home/QLFY233/Test-flight-control-system/plan.md, /home/QLFY233/Test-flight-control-system/progress.md]

对 frontend（vanilla JS 前端）做全面代码审查。工作目录：/home/QLFY233/Test-flight-control-system。

必须审查的文件：frontend/js/app.js, frontend/js/api.js, frontend/js/config.js, frontend/js/event-bus.js, frontend/js/router.js, frontend/js/sse.js, frontend/js/ws.js, frontend/js/state.js, frontend/js/shared.js, frontend/js/pages/*.js（OverviewPage/DashboardPage/AlphaPage/BetaPage/HistoryPage/SettingsPage）, frontend/js/components/*.js（ChatPanel/ChatMessage/FlightPlanCard/StatusBar/BottomBar/Toast/DashboardGrid/ConnectionOverlay/TimelineControl 等）, frontend/js/charts/*.js, frontend/serve.py, frontend/sw.js。

审查重点（按 code-review-skill 的 JS/通用质量/安全指南）：
1. 安全（最高优先级）：innerHTML/outerHTML 拼接用户或服务端数据导致的 XSS、事件消息内容渲染、iframe；
2. SSE/WS 客户端：重连逻辑（退避、指数）、心跳、断线状态恢复、事件监听器泄漏；
3. 状态管理：event-bus/state 的订阅-退订配对（addEventListener 后是否 remove）、内存泄漏；
4. DOM/计时器清理：setInterval/setTimeout 未清理、路由切换后旧组件未销毁、requestAnimationFrame 泄漏；
5. 错误处理：fetch 失败、JSON 解析 try/catch、Promise 未捕获拒绝；
6. 竞态：异步响应乱序覆盖 UI、快速切换页面时过期响应；
7. 代码质量：重复代码、魔法数、命名。

输出格式（写入报告）：按 🔴 blocking / 🟡 important / 🟢 nit / 💡 suggestion / 🎉 praise 分级，每条给出 `文件:行号` 与具体修改建议；结尾给出总体结论（Approve / Comment / Request Changes）与最重要的前 5 个问题。

---
Update progress at: /home/QLFY233/Test-flight-control-system/.pi-subagents/artifacts/progress/e6b96f0c/progress.md

---
**Output:**
Write your findings to exactly this path: /tmp/code-review/frontend-report.md
This path is authoritative for this run.
Ignore any other output filename or output path mentioned elsewhere, including output destinations in the base agent prompt, system prompt, or task instructions.

## Acceptance Contract
Acceptance level: attested
Completion is not accepted from prose alone. End with a structured acceptance report.

Criteria:
- criterion-1: Return concrete findings with file paths and severity when applicable

Required evidence: review-findings, residual-risks

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