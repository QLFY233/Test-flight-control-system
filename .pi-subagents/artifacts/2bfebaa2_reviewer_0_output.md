# backend-A / backend-B 并行修复独立验证报告（fresh context）

- 验证人：独立 reviewer（不信任修复者自测，逐项从代码/测试/文档取证）
- 验证基准：git HEAD `49158ef` + 工作区未提交修改（两侧修复均在未提交状态）
- 任务输入：`plan.md` / `progress.md` **不存在于仓库根**（`ls` 与 `find` 均未找到），按任务内联清单 + `/tmp/code-review/*.md` 四份报告执行
- 时间：2026-08-02（仓库内 clock）

---

## 逐项验证结果表

| # | 验证项 | 结果 | 证据 |
|---|---|---|---|
| 1 | backend-A 测试 56/56 | **PASS** | `cd backend-A && ../.venv-A/bin/python tests/test_all.py` → `A 侧测试结果: 56 通过 / 56 总数 ✅`；新增 Test 11-15 真实存在（Test 11 用 fake_call_ok/fake_call_error 断言 ok→executing、error→hovering，`tests/test_all.py:244-275`） |
| 2 | backend-B 测试 70/70 | **PASS** | `cd backend-B && ../.venv-B/bin/python tests/test_all.py` → `B 侧测试结果: 70 通过 / 70 总数 ✅`；含 B-1 无死锁残留、B-2 update_imu 写 _pose、B-5 初值、B-6 索引/并发等回归断言 |
| 3 | Python 3.8 AST 扫描 backend-B | **PASS** | `ast.parse(feature_version=(3,8))` 扫描 32 个 .py 文件，**0 违例** |
| 4 | shared/protocol.py 一致性 | **PASS** | 三处 `md5sum` 全同 `ee554c2a…`；A/B 侧均为 symlink → `../../shared/protocol.py`；`SCHEMA_VERSION = 2`（第 7 行）；git status 无 shared/protocol.py 修改 |
| 5a | B-1 on_imu 不再嵌套加锁 | **PASS** | `backend-B/rosbridge/subscriber.py:64-70`：`on_imu` 直接 `st.update_imu(accel, angular_vel, ts)`，无外层 `with st.pose_lock`；`state.py:93-95` docstring 明示"调用方不得再持有 pose_lock"，`update_imu` 单次加锁写 `_imu`+`_pose.accel/angular_vel` |
| 5b | A-B1 `_dispatch_action` 回退 hover | **PASS** | `backend-A/agents/alpha.py:184-205`：`msg_type==MSG_TYPE_ERROR or payload.status=="error" or payload.error` → `_send_hover()` + `last_llm_call_ok=False`；reject→hover；成功才置 EXECUTING。实现用 `==MSG_TYPE_ERROR` 而非 `!=result`——因为 `_send_and_wait` 正常 ack 返回 `{"status":"sent"}` 无 msg_type（`ipc/server.py:149-152`），若按 `!=result` 判失败会把每次成功下发误判为失败，当前判定对架构是正确的 |
| 5c | A-B2 broadcast 不再锁内 await send | **PASS** | `backend-A/web/ws.py:44-60`：锁内仅 `targets = list(_clients.items())` 快照，锁外 `queue.put_nowait`（非阻塞）；每客户端独立 sender task + 有界队列 256，队列满断开慢客户端（ws.py:19-42） |
| 5d | 🔴-3 abort 路由 | **PASS** | `backend-A/web/routes.py:219-249`：`POST /api/sessions/{session_id}/abort`，本地置 aborted + 清计划 + `bus_call(CALL_TOOL_ABORT)`，B 未连→502；**冒烟实测返回 502 + `{"detail":"abort dispatch failed: B not connected"}`** |
| 5e | 🔴-4 `_handle_status` 调 `_ws_status` | **PASS** | `backend-A/bus/bridge.py:175-193`：更新 flight_status 后 `await _ws_status(flight_status, mode, currentAction, totalActions)` |
| 5f | I1 常驻循环线程 | **PASS** | `backend-A/agents/alpha_llm.py:66-96`：`_ensure_loop()` 懒建 `asyncio.new_event_loop()` + `run_forever` daemon 线程；`translate` 用 `run_coroutine_threadsafe` + `fut.result(timeout=60)`；`close()` 停 loop；`AlphaLoop.stop` 调 `translator.close()`（alpha.py:92-94） |
| 5g | I8 默认绑 127.0.0.1 | **PASS** | `backend-A/main.py:93-97` 与 `run_a.py:11-13` 均 `os.environ.get("BACKEND_A_HOST", "127.0.0.1")`；冒烟实测监听 `127.0.0.1:8001` |
| 5h | B-2 run_b.py vel/accel 写 _pose | **PASS** | `backend-B/run_b.py:53-66`：`_on_velocity` 写 `st._pose.vel`（原 `lambda m: None` 已删）；IMU 走 `st.update_imu(...)` 写 `_pose.accel/angular_vel`；上行读 `p.vel[:]/p.accel[:]/p.angular_vel[:]` 不再恒零 |
| 5i | B-3 run_backend_b.sh | **PASS** | `run_backend_b.sh:24-27`：`cd "$SCRIPT_DIR/backend-B" && exec python main.py --config-dir "$SCRIPT_DIR/config"`；全文件无 `python -m backend_B`；`bash -n` 通过 |
| 5j | B-8 start_all.sh 无 nibuhao 残留 | **PASS** | `start_all.sh:8` `PROJ=$(cd "$(dirname "$0")" && pwd)`；全仓 grep `nibuhao` 仅剩注释与 .pi-subagents 工件；A 侧 python 改 `$PROJ/.venv-A/bin/python3`（start_all.sh:72） |

## 分歧/疑点裁决

| # | 裁决项 | 结果 | 证据 |
|---|---|---|---|
| 🟡-3 | broadcast_alpha_output 是否有调用点 | **PASS（已补，非遗漏）** | `agents/alpha.py:208` 下发成功后 `await self._broadcast_alpha_output(action_cmd)`；`:232-242` 实现 import 并调用 `web.ws.broadcast_alpha_output(action_cmd, goal, actions)`（goal 取动作序列里最后一个带 target 的）；ws.py:124-133 定义匹配。修复声明 alpha.py 行确实列了 🟡-3 |
| 🟡-4 | dispatch_b_event 是否校验 to | **PASS（已校验）** | `bus/bridge.py:69-76`：`_EVENT_EXPECTED_TO` 映射（pose/telemetry/status/reject→alpha、alert→beta，bridge.py:18-24），不匹配记 warning 并 return 丢弃 |
| B-12 | alert 的 to 应为何值 | **PASS（worker-B 正确，文档写 "beta"）** | 冻结文档 `docs/specs/总体/2026-07-05-A-B-接口冻结.md` **§3 表格第 80 行**：`\| alert \| "beta" \| monitor-trigger 处理:WS 推前端 alert(β 系统消息)+ 注入 β 上下文唤醒 β 给处置建议`；**§5 表格第 117 行**：`\| alert \| ... \| "beta" \| WS alert(...作 β 对话流系统消息)+ 唤醒 β`。B 侧 monitor/component.py:113 发 `"to": TO_BETA`，A 侧 bridge.py:23 期望 `TO_BETA`——两侧与文档一致。contract-report 建议改 alpha 系误读 |

## 集成冒烟（尽力而为）

| 端点 | 结果 | 证据 |
|---|---|---|
| 服务启动 | ⚠️ 见下（缺 key 无法裸启动） | 用 `DEEPSEEK_API_KEY=dummy-key-for-smoke-test` + `main.py --port 8001`（8000 被 Windows 侧 PID 40620 占用，见遗留问题）成功启动 |
| GET /api/health | 200 | `{"status":"ok","backend":"A"}` |
| GET /api/field/config | 200 | `{"boundary":{"x":[0.0,5.0],...},"home":{"position":[0.0,0.0,0.5],"yaw":0.0}}` |
| GET /api/sessions | 200 | 建会前 `{"sessions":[]}`，建会后返回该行 |
| POST /api/sessions | 200 | `{"id":"2026080214272676528","status":"idle","created_at":"..."}` |
| POST /api/sessions/{id}/abort | **502（符合预期）** | `{"detail":"abort dispatch failed: B not connected"}`——B 未连接时 502 属声明行为 |
| 启动日志行为 | ✅ | 无 key+dummy key 下 α/β agent 均创建；B 未连时 α loop 的 hover 下发走 `forward to B failed: B not connected` 错误日志并正确回退，进程不崩 |

冒烟副作用：`data/flight_control.db` 落了一行 session（该文件在 `.gitignore:20`，无仓库污染）；服务与临时 socket 已清理。

---

## 遗留问题清单

### 🔴 FAIL-1（回归，阻断"缺 API key 降级启动"预期）
- **位置**：`backend-A/lifecycle.py:97-101`（`_start_beta`）+ `backend-A/agents/beta.py:69`
- **证据**：无 .env/无 API key 时 `python backend-A/run_a.py` 实测崩溃退出：
  `openai.OpenAIError: Missing credentials...` → `ERROR: Application startup failed. Exiting.`（/tmp/verify-a.log）
- **根因**：I7 修复把 `_start_beta` 从 `logger.warning`（吞异常、服务器照常起）改为**无条件 raise**（git diff 证实原代码为 `logger.warning(f"[lifecycle] β agent not created: {e}")`）。β 走 `make_agent` → `OpenAIProvider` → `AsyncOpenAI(api_key="")` 抛 "Missing credentials"，而 `_start_beta` 没有像 `_start_alpha` 那样的 `"api_key"/"not set"` 白名单降级分支（lifecycle.py:84-91 有，β 分支没有）。
- **影响**：任务要求"缺 API key 时 lifecycle 应能降级启动"，实际**起不来**；与修复声明"缺 API key 白名单降级"不一致（α 降级了，β 没有）。对部署排障不友好：无 key 环境（先导/离线调试）无法启动 A 侧 REST/WS 全链路。
- **修复建议（仅建议，本次未改）**：`_start_beta` 的 except 分支复制 α 的白名单判定（`"api_key" in msg.lower() or "not set" in msg or "API key" in msg` → warning+return），其余异常仍 fail-fast。

### 🟡 NOTE-2（环境，非代码缺陷）
- 端口 8000 被 **Windows 侧** python 进程占用（`Get-NetTCPConnection` → PID 40620，`C:\Users\QLFY233\AppData\Local\Programs\Python\Python311\python.exe`，监听 `0.0.0.0:8000`）。WSL 内 `ss` 不可见、`bind` 报 EADDRINUSE。冒烟改在 8001 完成。与代码无关，但会真实阻断 start_all.sh 的 A 侧启动（fuser -k 8000/tcp 只清 WSL 内进程，清不掉 Windows 侧）。

### 🟢 NOTE-3（观察）
- `frontend/` 也有未提交修改（api.js/app.js/ws.js 等，属另一修复 worker 范围），本次仅验证 backend-A/B，未纳入判定；`frontend/js/escape.js` 为新增未跟踪文件。
- `backend-A/agents/__pycache__/` 出现 `cpython-38.pyc` 残留（.venv-A 是 3.10）——疑似曾用 3.8 解释器导入过 backend-A，无功能影响。
- `_handle_reject`（bridge.py:195-215）已完整实现 🟡-6：清 `current_action_plan` + `emergency_hover()` + WS reject 广播，实测代码路径闭合。

---

## 总体结论

**backend-A 修复：PASS（1 项新引入回归除外）**；**backend-B 修复：PASS**。

- 所有任务清单项（测试数、AST、协议一致性、10 项修复抽查）全部 PASS；
- 三个裁决项全部落定：🟡-3 调用点已补、🟡-4 to 校验已实现、B-12 文档写 "beta" 且两侧+文档三方一致（worker-B 判断正确）；
- 集成冒烟 5 端点全部符合预期（abort 未连 B 返回 502 属声明的可接受行为）；
- **唯一 FAIL**：I7 修复引入回归——无 API key 时 backend-A 无法启动（`_start_beta` 无条件 raise），违背任务"缺 key 应降级启动"与修复声明自身"白名单降级"意图。建议修复后复测。