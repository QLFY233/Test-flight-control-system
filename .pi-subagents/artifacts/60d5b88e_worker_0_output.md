# backend-A 修复报告（并行修复 worker-A）

- 修复范围：`backend-A/**`（不含 backend-B / frontend / shared/protocol.py / docs/specs / start_all.sh）
- 依据：`/tmp/code-review/backend-A-report.md` + `/tmp/code-review/contract-report.md` 中 backend-A 相关项
- 测试基线：修复前 47/47 → 修复后 **56/56 全绿**（新增 9 项测试覆盖）

---

## 改动文件清单（20 个）

| 文件 | 修复项 |
|---|---|
| agents/alpha.py | B1, 🟡-3, 🟡-6(emergency_hover), S3, N6, N8, N14 |
| agents/alpha_llm.py | I1, 契约🟢(SCHEMA_VERSION) |
| bus/bridge.py | 🔴-4, 🟡-4, 🟡-6, N1 |
| web/ws.py | B2, S2, 契约🟢(SCHEMA_VERSION) |
| web/routes.py | 🔴-3, I2, I8, 🟡-9, N4, N5, N14, 契约🟢(t_from/t_to) |
| web/sse.py | I8(限长), N14 |
| ipc/server.py | I5, N2, N3, 🟡-8 |
| db/repos.py | I3, I4 |
| db/session.py | N7(删死代码), N8(PRAGMA foreign_keys) |
| db/models.py | N13 |
| config_loader.py | S5 |
| speech/stt_client.py | N10 |
| speech/tts_client.py | N11 |
| analytics/fft.py | N12 |
| main.py | I8(默认回环), S1(CORS) |
| run_a.py | I6, I8 |
| lifecycle.py | I7 |
| state.py | S4 |
| monitor_trigger/trigger.py | N9（**删除**，死代码） |
| tests/test_all.py | 新增 Test 11-15 |

---

## 修复项对照表

| 编号 | 状态 | 验证方式 |
|---|---|---|
| 🔴 B1 下发失败误报 executing | done | Test 11：error ack → 回退 hovering；正常 ack → executing |
| 🔴 B2 WS 广播持锁 + 耦合 IPC | done | 每客户端有界队列 + 独立 sender task，broadcast 非阻塞 put_nowait；队列满断开慢客户端 |
| 🔴-3 abort 路由 | done | `POST /api/sessions/{id}/abort`：本地置 aborted + 经 bus 下发 call.abort，error 回 502 |
| 🔴-4 status 不转发 WS | done | `_handle_status` 补调 `_ws_status`（bridge.py） |
| 🟡 I1 LLM 跨 loop 复用 | done | alpha_llm.py 常驻事件循环线程（懒启动）+ close()；AlphaLoop.stop 调用 close |
| 🟡 I2 approve TOCTOU | done | Test 12：`s._lock` 内原子认领，二次 approve 抛 404 |
| 🟡 I3 TelemetryBuffer task | done | 保存 task 引用，stop() await 任务（替代 sleep 猜测） |
| 🟡 I4 批量插入整批丢 | done | Test 14：`INSERT OR IGNORE`，重复 t 只落 1 行 |
| 🟡 I5 IPC writer 泄漏 | done | finally 中 close + wait_closed（含帧超限路径） |
| 🟡 I6 run_a.py WARNING | done | 改 INFO + uvicorn log_level='info' |
| 🟡 I7 接线异常被吞 | done | 非白名单异常 logger.exception + raise（fail-fast）；缺 API key 白名单降级 |
| 🟡 I8 安全最小修复 | done | 默认绑 127.0.0.1（BACKEND_A_HOST 覆盖）；SSE message 与 approve intent 限长 4096；WS 单消息 64KiB |
| 🟡-6 reject 不注入 α | done | `_handle_reject` 清空 current_action_plan + `alpha_loop.emergency_hover()` |
| 🟡-8 ping 实现偏离文档 | done | ping 改 MSG_TYPE_CALL + call_id；pong 校验 to=='heartbeat' |
| 🟡-9 会话端点缺失 | done | 新增 POST /api/sessions、PATCH /api/sessions/{id}（GET 保持兼容） |
| 🟢 N1 bridge 解耦 | done | B2 队列化后无阻塞点，补注释 |
| 🟢 N2 IncompleteReadError 刷屏 | done | 降级 debug |
| 🟢 N3 frames 复用 | done | server 改用 `ipc.frames.encode_frame` |
| 🟢 N4 遥测截断 | done | 显式 `limit` 参数（默认 1000，le=10000） |
| 🟢 N5 list_sessions limit | done | `Query(10, le=100)` |
| 🟢 N6 ActionPlan 死代码 | done | alpha.py 改用类型化 ActionPlan（dataclass 复活） |
| 🟢 N7 get_session 死代码 | done | 删除 db/session.py get_session（全仓无调用） |
| 🟢 N8 session id + 孤儿行 | done | ns 级 session id；_log_action 显式 create_session；PRAGMA foreign_keys=ON |
| 🟢 N9 monitor_trigger 死代码 | done | 删除 trigger.py（保留空包目录与 spec 一致） |
| 🟢 N10 STT host/超时 | done | urlparse.netloc；finish(timeout=15s) wait_for 防挂起 |
| 🟢 N11 tts 未用 import | done | 移除 time/hashlib |
| 🟢 N12 FFT 边界 | done | Test 13：n<2 提前返回；DFT frequencies/magnitudes 同源同长，修 off-by-one |
| 🟢 N13 时区统一 | done | FlightSession.created_at 改 aware datetime |
| 🟢 N14 未用 import | done | routes.py/sse.py time、alpha.py json/time |
| 💡 S1 CORS | done | 白名单 localhost/127.0.0.1:3456 + :8000 |
| 💡 S2 WS 防御 | done | 畸形 JSON 回 error 帧不断连；限长 |
| 💡 S3 双 hover 去重 | done | _translate 不再发 hover，由 _loop 统一兜底 |
| 💡 S4 current_pose 拷贝 | done | 返回 PoseData 深拷贝（含列表） |
| 💡 S5 config print+exit | done | 改抛 FileNotFoundError/ValueError |
| 契约🟢 ws schema_version | done | 导入 SCHEMA_VERSION |
| 契约🟢 telemetry t_from/t_to | done | 参数改名（当前无调用点，安全） |

---

## 自测结果

```
.venv-A/bin/python backend-A/tests/test_all.py → 56 通过 / 56 总数 ✅
python3 -m py_compile（20 个改动文件）→ OK
全模块导入冒烟（22 个 backend-A 模块）→ IMPORT OK
git status：无 staged 文件
```

新增测试：Test 11（B1 状态机）、Test 12（I2 原子认领）、Test 13（N12 FFT 边界）、Test 14（I4 OR IGNORE）、Test 15（N8 session id 唯一性）。

---

## 残余风险

1. **I1（LLM 常驻循环线程）未实测**：本环境无 DeepSeek API key，未做双连发翻译实证；线程方案按 pydantic-ai 2.0 httpx loop-affinity 源码推断。上线前建议做两次连续 LLM 翻译验证。
2. **B2 队列化后语义变化**：慢客户端不再阻塞广播，但队列满（256 条 ≈ 25s）会主动断开该客户端——行为差异符合设计，需前端确认 WS 重连可接受。
3. **abort 路由**：B 未连接时返回 502（本地状态已置 aborted）；前端需处理 502 提示。
4. **N8 PRAGMA foreign_keys=ON**：遥测/会话写入现在强依赖先建 flight_sessions 行——`_log_action` 与 POST /api/sessions 已建行，但 `_handle_pose` 在 session_id 已设而行未建（极端竞态 <1s 窗口）时 flush 会失败并记日志（不崩溃）。
5. **monitor_trigger 目录保留**：仅删除 trigger.py（死代码），空 `__init__.py` 保留以对齐 design spec 目录结构。