# Task for reviewer

[Read from: /home/QLFY233/Test-flight-control-system/plan.md, /home/QLFY233/Test-flight-control-system/progress.md]

对 backend-B（飞控桥，Python）做全面代码审查。工作目录：/home/QLFY233/Test-flight-control-system。

必须审查的文件：backend-B/main.py, backend-B/run_b.py, backend-B/lifecycle.py, backend-B/state.py, backend-B/config_loader.py, backend-B/rosbridge/adapter.py, backend-B/rosbridge/node.py, backend-B/rosbridge/publisher.py, backend-B/rosbridge/subscriber.py, backend-B/rosbridge/topics.py, backend-B/monitor/component.py, backend-B/monitor/detector.py, backend-B/monitor/thresholds.py, backend-B/monitor/trends.py, backend-B/small_model/component.py, backend-B/small_model/goal_gen.py, backend-B/small_model/stub.py, backend-B/ipc/client.py, backend-B/ipc/dispatch.py, backend-B/ipc/frames.py, backend-B/bus/*.py。

审查重点（按 code-review-skill 的 Python 指南 + 并发指南）：
1. 线程/回调正确性：rosbridge 回调线程与主线程数据竞争、锁使用、GIL 之外的共享可变状态；
2. IPC 客户端：断线重连逻辑、消息帧编解码（msgpack）边界、超时处理；
3. monitor：阈值比较的边界条件（>= vs >）、时间窗口滑动、趋势算法正确性；
4. small_model：stub/component 的职责划分、状态机、错误路径；
5. 资源生命周期：rospy 订阅/发布器是否清理、线程是否 join；
6. Python 3.8 兼容性（禁止 3.9+ 语法如 dict | 合并、zoneinfo、removeprefix）；
7. 错误处理与日志：异常是否吞掉、连接失败是否有可诊断日志。

输出格式（写入报告）：按 🔴 blocking / 🟡 important / 🟢 nit / 💡 suggestion / 🎉 praise 分级，每条给出 `文件:行号` 与具体修改建议；结尾给出总体结论（Approve / Comment / Request Changes）与最重要的前 5 个问题。

---
Update progress at: /home/QLFY233/Test-flight-control-system/.pi-subagents/artifacts/progress/e6b96f0c/progress.md

---
**Output:**
Write your findings to exactly this path: /tmp/code-review/backend-B-report.md
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