# backend-B（飞控桥，Python 3.8 + ROS Noetic）全面代码审查报告

- 审查范围：backend-B 全部 24 个源文件（main/run_b/lifecycle/state/config_loader、rosbridge/*、monitor/*、small_model/*、ipc/*、bus/*）
- 审查依据：code-review-skill（Python 指南 + 并发指南）；项目约定 CLAUDE.md（schema_version=2、Python 3.8 锁定、specs 优先）
- 输入说明：任务指定的 `plan.md` / `progress.md` 在仓库根目录不存在（`ls` 与 `find` 均未找到），本次按代码与 git 历史独立审查。
- 验证：`tests/test_all.py` 直接运行 58/58 通过；`python3 ast.parse(feature_version=(3,8))` 全仓扫描无 3.9+ 语法；嵌套锁死锁已用等价复现脚本实证。

---

## 🔴 blocking

### B-1. `rosbridge/subscriber.py:65-68` — IMU 回调嵌套获取非重入锁，死锁（已实证）
```python
with st.pose_lock:                 # 第一次获取
    st._pose.accel = accel
    st._pose.angular_vel = angular_vel
    st.update_imu(accel, angular_vel, ts)   # update_imu 内部再次 with self.pose_lock
```
`state.py:40` 定义 `self.pose_lock = threading.Lock()`（**非重入**）。`state.py:79-83` 的 `update_imu` 再次 `with self.pose_lock`，同一线程二次获取 → 永久阻塞。已用等价复现脚本验证（回调 0.5s 内无法完成）。后果：生命周期路径（`main.py`/`run_backend_b.sh`）收到第一条 IMU 消息即挂死该回调线程，且锁被永久持有，随后 pose/velocity 回调全部阻塞，B 侧遥测整体冻结，monitor 持续报 `drone_data_stale` critical。
**修改建议**：`on_imu` 去掉外层 `with st.pose_lock` 直接调用 `st.update_imu(...)`（与 `run_b.py:53` 一致），或把 `update_imu` 改为不取锁的内部方法；若确实需要嵌套，改用 `threading.RLock`。二选一，避免两处取锁。

### B-2. `run_b.py:52-53, 65-66` — 生产入口（start_all.sh 实际调用）遥测/监控数据通路断裂
- `run_b.py:52`：`rospy.Subscriber(topics['local_velocity'], TwistStamped, lambda m: None)` — **速度消息被直接丢弃**，`BState._pose.vel` 恒为 `[0,0,0]`。
- `run_b.py:53-55`：IMU 回调只调 `st.update_imu(...)`，写入的是 `_imu`（`state.py:79-83`），**从不写 `_pose.accel`/`_pose.angular_vel`**。
- `run_b.py:65-66`：上行 pose/telemetry 事件读的是 `p.vel[:]`、`p.accel[:]`、`p.angular_vel[:]`（PoseData）——因此**生产路径下 A 收到的 vel/accel/angularVel 恒为全零**。
- 连带后果：`monitor/thresholds.py:38,70,80` 的 overspeed/overaccel/over_angular 检测与 `monitor/trends.py:34-48,61-68` 的 jerk/振荡检测全部失效（输入恒零）——**阶段 I 安全监控在生产入口下静默失效**。
- 与 lifecycle 路径（`subscriber.py` 的 on_velocity/on_imu 会写 `_pose.vel/accel`）行为不一致——双入口已发散。
**修改建议**：run_b.py 的 IMU 回调改走 `subscriber.DroneSubscriber`（或补充写 `_pose.accel/_pose.angular_vel`），velocity 订阅改为真实写入 `_pose.vel`；上行统一从 `current_pose`/`current_imu` 取数。推荐直接废弃 run_b.py、统一到 lifecycle 路径（见 B-3/💡）。

### B-3. `main.py:3` + `run_backend_b.sh:21` — 文档化入口 `python -m backend_B.main` 必然失败
`run_backend_b.sh` 执行 `exec python -m backend_B.main "$@"`，但仓库内不存在 `backend_B` 包（目录名为 `backend-B`，含连字符），已实测 `.venv-B/bin/python -c "import backend_B"` → `ModuleNotFoundError`。`main.py` 里把自身目录塞进 `sys.path` 只对 `python main.py` 有效，救不了 `-m` 解析。即 run_backend_b.sh 这条“现代入口”每次都直接崩。
**修改建议**：把包名与目录统一（重命名目录为 `backend_B`，或建 `backend_B` 软链/`sitecustomize`），或 `run_backend_b.sh` 改为 `cd backend-B && exec python main.py --config-dir ../config`。修复后需重新验证 B-1 的死锁（生命周期路径是唯一会触发 B-1 的路径）。

---

## 🟡 important

### B-4. `ipc/client.py:80-81` + `ipc/frames.py:47` — 非法帧/回调异常会永久杀死 recv 线程且无诊断日志
`recv_frame` 对 `msgpack.unpackb` 结果不做顶层类型校验（非 dict 也返回）；`recv_loop` 中 `self._on_frame(msg)` 未包 try/except。若 A 侧发来非 dict 顶层载荷（list/str），`dispatch.handle_incoming` 的 `msg.get` 抛 `AttributeError`，异常直接冒泡出 `recv_loop` → **daemon 线程静默死亡，不再重连、不再收任何消息**（仅 stderr 打印 traceback）。注意：组件内部异常已被 `bus/router.py:33-35` 兜住，但帧类型与 dispatch 层无兜底。
**修改建议**：`recv_loop` 内 `on_frame` 调用包 `try/except Exception: logger.exception(...)`；`recv_frame` 返回后校验 `isinstance(msg, dict)`，否则记错并抛 `ValueError` 走既有重连逻辑。

### B-5. 监控启动假阳性 — `monitor/component.py:71,92-98` + `monitor/thresholds.py:100-101` + `state.py:38`
`_last_data_ts` 初值 0.0，monitor 启动即跑 10Hz：首条 pose 到达前（rospy 订阅建立通常需 0.5~2s），`ts - 0 > 0.5` 即触发 `drone_data_stale` **critical**；而 critical 不节流（component.py:92-98），每 tick 上告一条，启动即向 A 刷屏。另外 `z=0 < floor(0.3)`（thresholds.py:61）在起飞前持续报 `floor_breach` warning。
**修改建议**：启动后标记“尚未收到首帧数据”，首帧前不评估 stale/floor/boundary；或 monitor `start()` 时将 `_last_data_ts` 初始化为 `time.time()`，并对 `drone_data_stale` 增加首次触发前的宽限期（如 2s）。

### B-6. `small_model/component.py:78-80, 87-110, 137-141` — 计划/索引跨线程无锁读写（TOCTOU）
IPC 线程（`_handle_generate_goal`/`_handle_abort`/`_handle_hover`）与 goal-publisher 线程（`check_arrival_and_advance` → `_advance_action` → `_generate_next_goal`）并发读写 `current_action_plan`/`current_action_index`/`small_model_status`，**无任何锁**（`self._lock` 只保护 `_current_goal`）。具体竞态：新计划写入（plan=新、index=0 分两次赋值）与 publisher 用旧目标做到达判定之间，可能发生 `_advance_action` 把新计划 index 从 0 推到 1 → **新计划首条动作被跳过**；或读到“新 plan + 旧 index”误判全部完成（component.py:90-95）→ 提前清空目标点、短暂悬停。
**修改建议**：将 `plan + index + status + _merged_safety` 的读写全部收敛到 `self._lock`（或单独一把状态锁），`_advance_action` 的 `index += 1` 与读 plan 在同一临界区内完成。

### B-7. `ipc/client.py:51-59, 36` — `send()` 持锁做阻塞 `sendall`
socket 被设为阻塞模式（`settimeout(None)`，client.py:36），`send()` 在整个 `sendall` 期间持有 `self._lock`。若 A 侧停止读取，sendall 阻塞在 TCP 发送缓冲，将连带卡死 `recv_loop` 的取 sock、`connect()`、`close()`（同锁）。多个发送方（uplink/monitor/goal/recv 线程的 pong）也被串行化放大延迟。
**修改建议**：发送移出锁外（取 sock 引用后放锁再 sendall），或对发送 socket 设短超时/非阻塞 + 失败即断连重连；至少注释说明锁内阻塞发送的前提。

### B-8. `start_all.sh:7, 66` — 硬编码 `/home/nibuhao/...` 路径（本机为 `/home/QLFY233/...`）
一键启动脚本指向另一台机器的家目录，在本机直接 `bash start_all.sh` 必然失败（backend-A 的 python 路径同样写死）。该文件不在必审清单内，但它正是 run_b.py 的调用方，直接影响 B 启动。
**修改建议**：`PROJ=$(cd "$(dirname "$0")" && pwd)` 自推导，删除 `/home/nibuhao/.pyenv/...` 硬编码。

---

## 🟢 nit

- **B-9. `subscriber.py:52-53`**：`on_velocity` 覆盖 `st._pose.ts`（用速度帧时间戳），pose 的 ts 语义被污染；且不更新 `_last_data_ts`。建议 velocity 只写 `_pose.vel`，不动 ts。
- **B-10. `lifecycle.py:246` vs `run_b.py:65`**：上行 payload 的 `ts` 语义不一致（`p.ts` vs `time.time()`）。统一为同一时钟源；注意若将来 `update_pose`（`state.py:69-73`）被启用，`_last_data_ts = ts`（header stamp）与 monitor 的 wall-clock 比较会错配，应统一 wall time。
- **B-11. `monitor/trends.py:42-47`**：jerk 是逐帧速度二阶差分，单位实为 “m/s·帧⁻²”，alert 文案写 `m/s³`；阈值 2.0 隐含依赖 10Hz 帧率。建议按 `dt` 归一化或改文案并注明帧率依赖。
- **B-12. `monitor/component.py:105`**：alert 事件 `"to": "beta"`，其余 B→A 事件均为 `"to": "alpha"`（run_b.py:64、lifecycle.py:233、small_model/component.py:222）。A 侧 `ipc/server.py:116` 按 tool 分发、不过滤 `to`，目前可工作，但与接口冻结 §5 约定不一致，建议统一为 `"alpha"`。
- **B-13. `rosbridge/publisher.py:37-41`**：`stop()` docstring 写“发最后一帧悬停”，实现只 join 线程、不发帧。实际悬停由 `lifecycle._shutdown` 的 bus hover 兜底，但文档与实现不符；要么补发要么改文档。
- **B-14. `run_b.py:69`**：`except: pass` 吞掉所有上行异常、无任何日志（对比 lifecycle.py:161-165 有 rate-limited error 日志）。至少改为 `except Exception as e: logger.warning(...)`。
- **B-15. `small_model/stub.py:108-110`**：`out_of_boundary_after_clamp` 终检是死代码（`_clamp_point` 恒把点夹回界内）；作防御保留可以，建议加注释说明。

## 💡 suggestion

- **B-16. 双入口合并**：`run_b.py`（start_all 用，遥测通路坏、无优雅关停）与 `lifecycle.py+main.py`（有完整 shutdown 序列、有监控线程管理，但入口损坏 + 死锁）已明显发散。建议以 lifecycle 为唯一规范入口，修复 B-1/B-3 后删除 run_b.py，避免双份维护与行为漂移。
- **B-17. `ipc/client.py:62-89`**：重连为固定 1s 轮询，先导可用；后续可加指数退避上限与重连次数日志，避免连接失败时静默循环刷 warning。
- **B-18. `state.py` 读侧**：`current_pose` 返回内部 `PoseData` 对象、读侧在锁外取 `p.pos[:]` 等多字段快照，单字段赋值原子、无撕裂写，但可能读到 “新 pos + 旧 ts” 的混合快照。可接受，建议加注释明确“非一致快照”语义，避免后续维护者误以为强一致。

## 🎉 praise

- **P-1. Python 3.8 兼容执行到位**：rospy 回调全部用闭包（subscriber.py 注释明示 3.8 动机）；`from __future__ import annotations` 覆盖所有 `X | None`/`dict[str, ...]` 注解文件；AST `feature_version=(3,8)` 全仓扫描零违例，无 `dict|`、`zoneinfo`、`removeprefix`。
- **P-2. 帧编解码健壮**（`ipc/frames.py`）：4 字节大端长度前缀 + 16MiB 上限在 unpack 前校验，`_recv_exact` 半包/断连处理正确，防 OOM/防粘包边界清晰；测试覆盖超限拒绝（test_all.py Test 2）。
- **P-3. 锁纪律总体良好**：高频位姿写路径统一走 `pose_lock`（subscriber.py/run_b.py），读侧切片拷贝；`bus/router.py:33-35` 将组件异常统一转 error result，避免组件 bug 打穿 IPC 线程（B-4 只剩帧类型与 dispatch 层缺口）。
- **P-4. 协议共享落地**：`bus/protocol.py` 软链 → `shared/protocol.py`，diff 逐字一致，`SCHEMA_VERSION=2` 与 CLAUDE.md 变更控制一致。
- **P-5. monitor 架构可扩展**：Detector ABC + 注册表（`monitor/detector.py`），同 code 2s 节流、critical 免节流的分级策略合理；`drone_data_stale` 用 `last_data_ts` 判停产的思路正确（问题只在启动初值与 B-5）。
- **P-6. 测试自洽**：`tests/test_all.py` 58/58 通过（协议常量、帧编解码含边界、配置校验、BState、总线注册/路由、IPC 帧类型），单文件可跑、无 pytest 依赖。

---

## 总体结论：**Request Changes**

两个 🔴 阻塞项都落在“生产/文档化启动路径”上（run_b 路径监控与遥测静默失效；lifecycle 路径入口不可用 + 死锁），必须先修；其余 🟡 集中在并发边界与启动假阳性，属同一批修复可覆盖。

### 最重要的前 5 个问题
1. **B-1（🔴）** `subscriber.py:65-68` 嵌套获取非重入 `pose_lock` → IMU 首帧即死锁，整链遥测冻结（已实证）。
2. **B-2（🔴）** `run_b.py:52-53,65-66` 生产入口丢速度、accel 只写 `_imu` 而上行读 `_pose` → vel/accel 恒零、monitor 安全检测全部失效。
3. **B-3（🟡）** `main.py:3` / `run_backend_b.sh:21` `python -m backend_B.main` 模块名不存在，文档化入口必然失败。
4. **B-4（🟡）** `ipc/client.py:80-81` 非法帧/回调异常杀死 recv 线程且无日志、不重连。
5. **B-5（🟡）** monitor 启动即刷 critical `drone_data_stale` + `floor_breach` 假阳性（`_last_data_ts` 初值 0 + critical 不节流）。