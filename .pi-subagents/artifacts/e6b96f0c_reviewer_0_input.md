# Task for reviewer

[Read from: /home/QLFY233/Test-flight-control-system/plan.md, /home/QLFY233/Test-flight-control-system/progress.md]

对 backend-A（Agent 中枢，Python）做全面代码审查。工作目录：/home/QLFY233/Test-flight-control-system。

必须审查的文件：backend-A/main.py, backend-A/run_a.py, backend-A/lifecycle.py, backend-A/state.py, backend-A/config_loader.py, backend-A/agents/alpha.py, backend-A/agents/alpha_llm.py, backend-A/web/routes.py, backend-A/web/ws.py, backend-A/web/sse.py, backend-A/tools/beta_tools.py, backend-A/speech/stt_client.py, backend-A/speech/tts_client.py, backend-A/analytics/fft.py, backend-A/analytics/filter.py, backend-A/ipc/server.py, backend-A/ipc/*.py, backend-A/bus/bridge.py, backend-A/db/repos.py。

审查重点（按 code-review-skill 的 Python 与 FastAPI 指南）：
1. 异步正确性：async 函数内是否有阻塞调用、asyncio 任务生命周期（未 await 的 task、后台任务泄漏）、SSE/WS 长连接资源释放；
2. 错误处理：异常吞噬、fail-fast 原则、日志是否完整；
3. 并发与竞态：共享状态（state.py）多协程访问、IPC server 并发；
4. 安全：Web 输入验证、SSE/WS 消息注入、敏感数据；
5. Python 3.8 兼容性（项目锁定 3.8，注意 walrus/f-string 等没问题但 dataclass slots、match 语句、zoneinfo 等 3.9+/3.10+ 特性）；
6. 资源生命周期：db/ipc/websocket 连接是否关闭、异常路径；
7. 代码质量：命名、重复、参数蔓延、字符串型代码。

输出格式（写入报告）：按 🔴 blocking / 🟡 important / 🟢 nit / 💡 suggestion / 🎉 praise 分级，每条给出 `文件:行号` 与具体修改建议；结尾给出总体结论（Approve / Comment / Request Changes）与最重要的前 5 个问题。

---
Update progress at: /home/QLFY233/Test-flight-control-system/.pi-subagents/artifacts/progress/e6b96f0c/progress.md

---
**Output:**
Write your findings to exactly this path: /tmp/code-review/backend-A-report.md
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