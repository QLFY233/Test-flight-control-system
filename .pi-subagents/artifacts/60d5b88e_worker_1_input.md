# Task for worker

[Read from: /home/QLFY233/Test-flight-control-system/context.md, /home/QLFY233/Test-flight-control-system/plan.md]

You are a delegated subagent running from a fork of the parent session. Treat the inherited conversation as reference-only context, not a live thread to continue. Do not continue or answer prior messages as if they are waiting for a reply. Your sole job is to execute the task below and return a focused result for that task using your tools.

Task:
修复 backend-B（飞控桥，Python 3.8 + ROS）全部审查问题。先读报告 /tmp/code-review/backend-B-report.md 和 /tmp/code-review/contract-report.md 中涉及 backend-B 的部分。项目根 /home/QLFY233/Test-flight-control-system。

【文件边界】只允许改 backend-B/**、backend-B/tests/**、start_all.sh、run_backend_b.sh（若存在，找一下根目录）；禁止改 backend-A/**、frontend/**、shared/protocol.py、docs/specs/。Python 3.8 语法硬约束（可再跑 AST 扫描验证）。

【必须修复】
🔴 B-1：rosbridge/subscriber.py:65-68 — IMU 回调嵌套获取非重入 pose_lock 死锁：去掉外层 with，直接调 st.update_imu()（与 run_b.py 一致）。
🔴 B-2：run_b.py:52-66 — 生产入口数据通路修复：velocity 订阅真实写入 _pose.vel；IMU 回调补写 _pose.accel/_pose.angular_vel（或改走 subscriber.DroneSubscriber）；上行统一从 current_pose/current_imu 取数。
🔴 B-3：run_backend_b.sh（或 start_all.sh 中相应片段）— python -m backend_B.main 模块名不存在（目录名 backend-B 含连字符）：改为 cd backend-B && exec python main.py 方式，并确保 start_all.sh 调用链一致。
🟡 B-4：ipc/client.py:80-81 — recv_loop 内 on_frame 包 try/except logger.exception；recv_frame 校验顶层是 dict 否则记错抛 ValueError 走重连。
🟡 B-5：monitor/component.py:71,92-98 + thresholds.py:100-101 — 启动首帧前不评估 stale/floor/boundary（_last_data_ts 初始为 time.time() 或加首帧标志+宽限期）。
🟡 B-6：small_model/component.py — plan/index/status 跨线程无锁 TOCTOU：读写全部收敛到 _lock（或单独状态锁），_advance_action 的 index+=1 与读 plan 同一临界区。
🟡 B-7：ipc/client.py:51-59,36 — send() 持锁阻塞 sendall：保持锁以保帧完整性（多发送方交错会坏帧），改为给 socket 设短超时（如 5s）+ 超时即断连重连；或在任务书中注释权衡。
🟡 B-8：start_all.sh:7,66 — 硬编码 /home/nibuhao/ 改为 PROJ=$(cd "$(dirname "$0")" && pwd) 自推导，python 路径同样处理。
🟡-5：small_model/component.py:199 与 stub.py:129 — reject reason 用 shared/protocol.py 常量 REJECT_UNKNOWN_ACTION_CODE（detail 里附编码）。
🟡-7：lifecycle.py:248-262 与 run_b.py:66-68 — telemetry payload 按冻结文档补 vel/imu 字段（{vel, accel, imu, ts}，去掉多余的 angularVel 或保留但补全）。
🟢 B-9~B-15 全部：B-9 subscriber.py on_velocity 不覆盖 _pose.ts、更新 _last_data_ts；B-10 上行 ts 统一 wall time；B-11 trends.py jerk 按 dt 归一化或改文案注明帧率；B-12 monitor alert 事件 to 统一 'alpha'（与冻结约定一致）；B-13 publisher.py stop() 文档与实现对齐（补发悬停帧或改文档）；B-14 run_b.py:69 except: pass 加日志；B-15 stub.py 死代码加注释。
💡 B-16：run_b.py 与 lifecycle 行为对齐（修复后双入口行为一致即可，不强制删文件）；B-17 重连加指数退避（上限 30s）+ 重连计数日志；B-18 state.py current_pose 加非一致快照注释。
契约 🟢：dispatch.py _handle_call 未用变量清理；ipc/client.py 断连时显式触发 small_model hover（_handle_hover）。

【自测】从 backend-B 目录跑 .venv-B/bin/python tests/test_all.py（当前 58/58 必须保持全绿）；全仓 AST feature_version=(3,8) 扫描零违例；python3 -m py_compile 所有改动文件。B-1 死锁修复后建议用等价脚本验证回调可完成。
【输出】写入 /tmp/code-review/fix-backend-B.md：改动文件清单、修复项对照表（编号→状态 done/skip+原因→验证方式）、自测结果、残余风险。禁止使用 WebSearch。

---
Update progress at: /home/QLFY233/Test-flight-control-system/.pi-subagents/artifacts/progress/60d5b88e/progress.md

---
**Output:**
Write your findings to exactly this path: /tmp/code-review/fix-backend-B.md
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