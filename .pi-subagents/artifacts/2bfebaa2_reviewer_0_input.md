# Task for reviewer

[Read from: /home/QLFY233/Test-flight-control-system/plan.md, /home/QLFY233/Test-flight-control-system/progress.md]

独立验证 backend-A 与 backend-B 的并行修复（fresh context，不信任修复者自测）。项目根 /home/QLFY233/Test-flight-control-system。参考 /tmp/code-review/backend-A-report.md、backend-B-report.md、contract-report.md（审查发现）、/tmp/code-review/fix-backend-A.md、fix-backend-B.md（修复声明）。

【必做验证】
1. 运行 backend-A 测试：cd backend-A && ../.venv-A/bin/python tests/test_all.py（须 56/56 全绿）；
2. 运行 backend-B 测试：cd backend-B && ../.venv-B/bin/python tests/test_all.py（须 70/70 全绿）；
3. Python 3.8 AST 扫描 backend-B 全部源文件零违例；
4. shared/protocol.py 与两侧软链仍逐字一致，SCHEMA_VERSION==2 未被动过；
5. 抽查修复真实性（不只看测试）：
   - B-1：subscriber.py on_imu 不再嵌套加锁；
   - A-B1：alpha.py _dispatch_action 对 msg_type!='result' 或 status=='error' 回退 hover；
   - A-B2：ws.py broadcast 不再锁内 await send；
   - 🔴-3：routes.py 有 POST /api/sessions/{id}/abort；
   - 🔴-4：bridge.py _handle_status 调用 _ws_status；
   - I1：alpha_llm.py 常驻循环线程方案真实存在；
   - I8：main.py/run_a.py 默认绑定 127.0.0.1；
   - B-2：run_b.py velocity/accel 写入 _pose；
   - B-3：run_backend_b.sh 不再用 python -m backend_B.main；
   - B-8：start_all.sh 无 /home/nibuhao 残留。
6. 裁决两个分歧/疑点：
   - 🟡-3（contract-report 🔴/🟡 部分）：broadcast_alpha_output 是否仍有调用点？（修复声明未列，疑似遗漏——若仍无调用点，判 FAIL 并给证据）
   - 🟡-4：bridge.py dispatch_b_event 是否校验 to 字段？（修复声明含糊）
   - B-12：读 docs/specs/总体/2026-07-05-A-B-接口冻结.md §3/§5，裁决 alert 的 to 应为何值（worker-B 声称文档写 beta，审查报告建议 alpha）——以文档原文为准。
7. 集成冒烟（尽力而为）：若可行，起 backend-A 服务（.venv-A/bin/python backend-A/run_a.py 或 main.py，注意缺 API key 时 lifecycle 应能降级启动），curl 验证：GET /api/health、GET /api/field/config、GET /api/sessions、POST /api/sessions（建一个）、POST /api/sessions/{id}/abort 的响应码与 JSON 形状；B 未连接时 abort 返回 502 或等价错误可接受。若服务起不来，记录原因（不算 FAIL，算环境限制）。

【输出】/tmp/code-review/verify-backend.md：逐项验证结果表（PASS/FAIL/ENV-LIMIT + 证据），遗留问题清单（若有 FAIL 给出文件:行号与证据）。禁止修改任何代码（只读验证）。禁止使用 WebSearch。

---
Update progress at: /home/QLFY233/Test-flight-control-system/.pi-subagents/artifacts/progress/2bfebaa2/progress.md

---
**Output:**
Write your findings to exactly this path: /tmp/code-review/verify-backend.md
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