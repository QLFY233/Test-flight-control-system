# Task for reviewer

[Read from: /home/QLFY233/Test-flight-control-system/plan.md, /home/QLFY233/Test-flight-control-system/progress.md]

做 A/B 跨进程协议与接口一致性审查（契约审查，不是常规 bug 审查）。工作目录：/home/QLFY233/Test-flight-control-system。

背景：项目有双进程架构 —— backend-A（Agent 中枢）与 backend-B（飞控桥）经 Unix socket + msgpack 通信；`docs/specs/总体/2026-07-05-A-B-接口冻结.md` 是接口冻结权威文档，当前 `schema_version = 2`，字段级变更必须两侧同步。

必须审查的文件：
- backend-A/bus/protocol.py 与 backend-B/bus/protocol.py（对比 schema_version、消息类型、字段定义是否完全一致）
- backend-A/ipc/server.py 与 backend-B/ipc/client.py、backend-B/ipc/frames.py、backend-B/ipc/dispatch.py（帧格式、握手、心跳、错误码是否对称）
- backend-A/web/routes.py、backend-A/web/sse.py、backend-A/web/ws.py 与 frontend/js/api.js、frontend/js/sse.js、frontend/js/ws.js（HTTP 端点、SSE 事件名、WS 消息格式、字段名是否一致）
- docs/specs/总体/2026-07-05-A-B-接口冻结.md（以它为权威基准，对照代码是否偏离）
- 也读 docs/specs/README.md 了解阅读顺序，docs/specs/总体/开放式接口规范.md（如存在）

审查重点：
1. schema_version 两侧常量是否一致且与文档一致；
2. 消息类型/事件名枚举两侧是否完全对齐（缺一个/多一个都算）；
3. 字段名、类型、单位、状态机状态取值两侧是否一致；
4. 前端调用的 API 路径、请求/响应 JSON 字段与后端路由实现是否一致；
5. 发现文档与代码的偏离点（以 docs/specs 为准标记）。

输出格式（写入报告）：按 🔴 blocking（两侧不一致/文档偏离）/ 🟡 important / 🟢 nit 分级，每条给出 `文件:行号 ↔ 文件:行号` 对照与修复建议；结尾列出『一致性检查表』：每个消息类型/事件名一行，标注 ✅ 一致 / ❌ 不一致 / ⚠️ 存疑。

---
Update progress at: /home/QLFY233/Test-flight-control-system/.pi-subagents/artifacts/progress/e6b96f0c/progress.md

---
**Output:**
Write your findings to exactly this path: /tmp/code-review/contract-report.md
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