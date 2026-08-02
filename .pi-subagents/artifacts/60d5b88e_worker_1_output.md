# backend-B 修复报告（worker-B）

修复范围：backend-B/** + start_all.sh + run_backend_b.sh（严格边界，未触碰 backend-A/、frontend/、shared/protocol.py、docs/specs/）。

## 改动文件清单（16 个）

| 文件 | 修复项 |
|---|---|
| backend-B/state.py | B-1(配合)、B-2(配合)、B-5、B-10、B-18 |
| backend-B/rosbridge/subscriber.py | B-1、B-2(配合)、B-9 |
| backend-B/run_b.py | B-2、B-14、🟡-7、契约断连hover、B-10 |
| backend-B/ipc/client.py | B-4、B-7、B-17、契约断连handler |
| backend-B/ipc/dispatch.py | 契约🟢 未用变量 |
| backend-B/monitor/component.py | B-5、SCHEMA_VERSION 常量（to 保持 beta，见下） |
| backend-B/monitor/thresholds.py | B-5 |
| backend-B/monitor/trends.py | B-11 |
| backend-B/rosbridge/publisher.py | B-13 |
| backend-B/small_model/component.py | B-6、🟡-5、SCHEMA_VERSION 常量 |
| backend-B/small_model/stub.py | 🟡-5、B-15 |
| backend-B/lifecycle.py | 🟡-7、B-10、契约断连hover、SCHEMA_VERSION 常量 |
| backend-B/main.py | B-3 |
| backend-B/tests/test_all.py | 新增 12 项回归测试 |
| start_all.sh | B-8 |
| run_backend_b.sh | B-3 |

## 修复项对照表

| 编号 | 级别 | 状态 | 修复方式 | 验证 |
|---|---|---|---|---|
| B-1 死锁 | 🔴 | done | subscriber.on_imu 去掉外层 `with st.pose_lock`，直接调 `update_imu`（单次加锁）；`update_imu` 在同一临界区写 `_imu` + `_pose.accel/angular_vel` | 测试 Test4 回归（锁可获取、无死锁残留） |
| B-2 数据通路 | 🔴 | done | run_b.py velocity 订阅真实写 `_pose.vel`（原丢弃）；IMU 走 `update_imu` → `_pose.accel/angular_vel` 同步更新 → 上行不再恒零 | Test4 回归 `update_imu 写 _pose.accel/angular_vel` |
| B-3 入口 | 🔴 | done | run_backend_b.sh 改 `cd backend-B && exec python main.py --config-dir <abs>/config`；main.py docstring 更新 | `python main.py --help` 正常解析；bash -n 通过 |
| B-4 recv 健壮 | 🟡 | done | recv_loop 校验顶层 dict（非 dict 抛 ValueError 走重连）；on_frame 包 try/except + logger.exception | py_compile + 代码审查 |
| B-5 启动假阳性 | 🟡 | done | `_last_data_ts` 初值 = time.time()；`data_received` 标志，monitor sample 携带，首帧前 thresholds 直接 return []；floor_breach 加 z>1cm 贴地豁免 | Test4 回归 `初始 data_received == False` / `last_data_ts > 0` |
| B-6 锁收敛 | 🟡 | done | plan/index/status/_merged_safety/_current_goal 读写全收敛到 `self._lock`；generate 写入+首条翻译同临界区；advance 的 index+=1 与读 plan 同临界区；check_arrival 判定+推进同临界区（无嵌套获取） | Test4 回归 generate/advance 索引正确 + 4 线程并发无异常 |
| B-7 send 阻塞 | 🟡 | done | socket 5s 短超时替代阻塞模式（锁内 sendall 保留以保帧完整性，超时抛异常 → 断连重连）；注释说明权衡 | py_compile + 代码审查 |
| B-8 硬编码路径 | 🟡 | done | start_all.sh `PROJ=$(cd "$(dirname "$0")" && pwd)`；A 侧 python 改 `$PROJ/.venv-A/bin/python3` | bash -n；grep 无残留 |
| B-9 velocity ts | 🟢 | done | on_velocity 不覆盖 `_pose.ts`，改刷 `_last_data_ts` + `_data_received` | 代码审查 |
| B-10 ts 统一 | 🟢 | done | lifecycle pose/telemetry payload ts 统一 `time.time()`（wall time），与 run_b 一致；`update_pose` 的 `_last_data_ts` 同步改 wall time | 代码审查 |
| B-11 jerk 文案 | 🟢 | done | 文案改 `m/s·帧⁻² (10Hz)`，注释帧率依赖 | 代码审查 |
| B-12 alert to | 🟢 | **skip（有意）** | 冻结文档 §3 表格明确 `alert → "beta"`（作 β 对话流系统消息），当前实现即 beta，与文档一致；审查建议改 alpha 系误读，保持不动，加注释说明 | grep 冻结文档 §3 |
| B-13 stop 文档 | 🟢 | done | docstring 改为实际行为（只 join，悬停由 lifecycle 兜底） | 代码审查 |
| B-14 except:pass | 🟢 | done | run_b uplink 改 `except Exception as e: print(...)` | 代码审查 |
| B-15 死代码 | 🟢 | done | stub 终检加防御注释 | 代码审查 |
| B-16 双入口 | 💡 | done(部分) | 数据通路已对齐（vel/accel/telemetry/断连hover 双入口一致）；保留双文件不强制删除 | 代码审查 |
| B-17 指数退避 | 💡 | done | 重连 1s→30s 指数退避 + 连接失败计数日志 | 代码审查 |
| B-18 快照注释 | 💡 | done | current_pose 加非一致快照语义注释 | 代码审查 |
| 🟡-5 reject 常量 | 🟡 | done | reject reason 用冻结常量（unknown_action_code / out_of_boundary_after_clamp），编码信息附新增 detail 字段；stub 错误消息用常量前缀，component `_normalize_reject` 拆分 | 代码审查 |
| 🟡-7 telemetry | 🟡 | done | lifecycle + run_b payload 补 `vel`/`imu` 字段（保留 angularVel 冗余向后兼容） | 代码审查 |
| 契约🟢 dispatch 变量 | 🟢 | done | 删未用 `to` 变量 | py_compile |
| 契约🟢 断连hover | 🟢 | done | IpcClient 加 disconnect handler，lifecycle/run_b 注册 → 断连时 small_model 切 hover | 代码审查 |

## 自测结果

- ✅ `../.venv-B/bin/python tests/test_all.py` → **70/70 通过**（原 58 + 新增 12 项回归：B-1 锁无残留、B-2 update_imu 写 _pose、B-5 data_received/初始 last_data_ts、B-6 generate/advance 索引 + 并发无异常）
- ✅ AST `feature_version=(3,8)` 全 backend-B 扫描零违例
- ✅ 全部改动文件 `python3 -m py_compile` 通过
- ✅ `python main.py --help` 正常（B-3 入口导入链 OK）
- ✅ `bash -n` start_all.sh / run_backend_b.sh 通过

## 残余风险

1. **B-1/B-2 的真机验证依赖 ROS 环境**：单元层已回归验证锁纪律与数据写入，但 subscriber 闭包回调与 rospy 消息解包的端到端验证需在 start_all.sh 全链路（roscore + sim-drone + B）下执行，本环境无 ROS 未跑。
2. **B-7 的 5s 超时语义变化**：recv 现在也会 5s 超时。A 侧 2s ping 保证正常情况 5s 内有数据；但若 A 侧暂停 ping（如 CPU 卡死），B 将每 5s 断连重连一次并触发断连 hover —— 属于防御性行为，可接受。
3. **B-6 锁内上行**：`_send_status`/`_send_reject` 在状态锁内触发 IPC send（5s 超时兜底）。正常路径毫秒级，可接受；极端下会短暂阻塞状态推进。
4. **telemetry 新增 `imu`/`vel` 字段**：A 侧 `_handle_telemetry` 先导仅日志，无兼容风险；后续入库实现需按冻结 §5.1 字段消费。
5. **monitor 首帧前不评估**：若 rospy 订阅永久失败（无数据），`drone_data_stale` 将不再告警（首帧前跳过）——这是有意的（避免启动假阳性），但意味着"订阅建立失败"本身需要靠 start_all.sh 的 READY 检查兜底，monitor 不再覆盖此场景。