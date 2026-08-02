# Task for worker

[Read from: /home/QLFY233/Test-flight-control-system/context.md, /home/QLFY233/Test-flight-control-system/plan.md]

You are a delegated subagent running from a fork of the parent session. Treat the inherited conversation as reference-only context, not a live thread to continue. Do not continue or answer prior messages as if they are waiting for a reply. Your sole job is to execute the task below and return a focused result for that task using your tools.

Task:
修复 backend-A（Agent 中枢）全部审查问题。先读报告 /tmp/code-review/backend-A-report.md 和 /tmp/code-review/contract-report.md 中涉及 backend-A 的部分。项目根 /home/QLFY233/Test-flight-control-system。

【文件边界】只允许改 backend-A/**、backend-A/tests/**（如需补测试）；禁止改 backend-B/**、frontend/**、shared/protocol.py、docs/specs/（除非有充分理由并在报告说明）。start_all.sh 由另一个 worker 负责，不要碰。

【必须修复】
🔴 B1：agents/alpha.py:163-181 + bus/router.py:24-31 — _dispatch_action 校验 result.msg_type=='result' 且 status!='error'，失败 logger.error + 回退 hover；reject 判定改为依赖 _handle_reject 状态回调而非调用返回值。
🔴 B2：web/ws.py:28-41 + bus/bridge.py:115-133 — 锁内只做 _connected 快照，锁外并发 await send；把广播从 IPC 收帧路径解耦（10Hz pose 广播入队或至少不阻塞收帧循环）。
🔴-3：web/routes.py 补 POST /api/sessions/{id}/abort 路由（经 bus 下发 call.abort，B 侧已支持）。
🔴-4：bus/bridge.py:87-90 _handle_status 补调 _ws_status 转发 WS（broadcast_status 已有实现）。
🟡 I1：agents/alpha_llm.py:60 — asyncio.run 每次新建 loop 复用 loop-affine httpx 客户端的问题：为 α 建常驻事件循环线程（new_event_loop + run_forever + run_coroutine_threadsafe），或每次调用重建 Agent；选稳健方案并注释原因。
🟡 I2：web/routes.py:81-100 approve_proposal TOCTOU — 用『先置空后处理』原子认领 pending_proposal（加锁或立即置 None）。
🟡 I3：db/repos.py:147-157 TelemetryBuffer — 保存 flush task 引用，stop() 用取消+await 替代 sleep 猜测。
🟡 I4：db/repos.py:179-191 — 批量插入改 OR IGNORE 或按 (session_id,t) 去重，防单条冲突丢整批。
🟡 I5：ipc/server.py:59-77 — finally 中 writer.close()（+wait_closed），帧超限路径也关闭。
🟡 I6：run_a.py:7,10 — log_level='info' 且 basicConfig INFO（与 main.py 对齐）；注意 start_all.sh 由他人改。
🟡 I7：lifecycle.py:81-124 — 非预期异常 logger.exception + 接线类错误 fail-fast；白名单降级路径（缺 API key）明确列出。
🟡 I8：安全最小修复（不引入共享密钥以免破坏前端）：默认绑定 127.0.0.1（支持环境变量覆盖）+ SSE ChatRequest.message 与意图类输入加长度上限（如 4096）；在 run_a.py/main.py 注释说明。
🟡-6：bus/bridge.py:93-104 _handle_reject — 清空/标记 A 侧 current_action_plan 并注入 α 队列或直接下发 call.hover。
🟡-8：ipc/server.py:136-150 — ping 改为 msg_type=CALL（文档冻结为 call.ping），pong 校验 to=='heartbeat'。
🟡-9：web/routes.py 按前端 spec 补 POST /api/sessions（create，可简单实现）与 PATCH /api/sessions/{id}；保持现有 GET /api/sessions 兼容。
🟢 N1~N14 全部：N1 bridge 解耦注释；N2 ipc/server.py IncompleteReadError 降级 debug 日志；N3 ipc/frames.py 复用一份实现（server 内联逻辑改用 frames）；N4 routes.py 遥测截断加注释/limit 参数；N5 list_sessions limit 用 Query(le=100)；N6 state.py ActionPlan 死代码删除或 alpha.py 改用 dataclass（推荐后者，若改动大则删除死代码）；N7 db/session.py get_session 删除或修正 docstring；N8 _log_action：细粒度 session id + 显式调用 create_session 建行 + SQLite 开 PRAGMA foreign_keys（连接处统一设置）；N9 monitor_trigger 死代码删除或接入（推荐删除并注明）；N10 stt_client host 提取与 finish 超时（加 timeout 参数）；N11 tts_client 未用 import；N12 analytics/fft.py 空数组/长度不一致边界；N13 db/models.py 统一 timezone.utc；N14 未用 import。
💡 S1：main.py 加 CORSMiddleware 白名单（localhost:3456 + localhost:8000 同源）；S2 web/ws.py json.loads 失败回 error 帧 + 单消息限长；S3 alpha.py 双 _send_hover 去重；S4 state.py current_pose 返回浅拷贝；S5 config_loader print+exit 改抛异常。
契约 🟢：ws.py 硬编码 schema_version 改从 shared/protocol.py 导入；web/routes.py 遥测参数 t_start/t_end 改名 t_from/t_to 对齐 spec（当前无调用点）。

【自测】从 backend-A 目录跑 .venv-A/bin/python tests/test_all.py（当前 47/47 必须保持全绿）；新增的 abort/会话路由若可测则补测试；改完逐个文件 python3 -m py_compile 检查。
【输出】写入 /tmp/code-review/fix-backend-A.md：改动文件清单、修复项对照表（编号→状态 done/skip+原因→验证方式）、自测结果、残余风险。禁止使用 WebSearch。

---
Update progress at: /home/QLFY233/Test-flight-control-system/.pi-subagents/artifacts/progress/60d5b88e/progress.md

---
**Output:**
Write your findings to exactly this path: /tmp/code-review/fix-backend-A.md
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