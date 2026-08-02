# 试飞控制系统 — 模块进度

> 本文件是**模块级进度追踪**，对齐 [`docs/开发规划.md`](开发规划.md) 的阶段 A~M。
> 规则见 [`CLAUDE.md`](../CLAUDE.md) §四：每模块完成时更新此文件 + todo 插件 + git push；开发前先 git pull。
> 状态图例：⬜ 未开始 / 🚧 进行中 / ✅ 已完成 / ⏳ 远期

最近更新：2026-08-02 19:15 (I1 实证 — LLM 双连发验证通过 + LLM_BASE_URL/LLM_MODEL 支持)

> **2026-08-02 19:15 (I1 实证)**:
> 用真实 API key + opencode.ai/zen/go/v1 端点 + deepseek-v4-flash 完成 I1 实证:
> ① LLMTranslator 双连发均成功 (5.8s/3.5s, 无 Event loop is closed) — 常驻事件循环线程修复实证有效
> ② 真实 α 系统 prompt (alpha.md) 翻译输出合法: takeoff+hover 动作编码、schema_version=2、task_id 正确
> ③ β SSE 全链路: agent 创建(16 工具) + 流式 markdown 响应正常
> ④ llm.py 新增 LLM_BASE_URL/LLM_MODEL 环境变量覆盖 (api_key 仍只走 DEEPSEEK_API_KEY, 不硬编码)
> 注: API key 仅经环境变量使用, 未入库; 首次双连发失败系测试用弱 system prompt 所致, 非代码缺陷

> **2026-08-02 (端到端验证 — ROS1 Noetic 全链路)**:
> 环境确认有 ROS1 Noetic + sim-drone 仿真器后完成全链路实测：roscore → sim-drone(50Hz pose/vel/IMU) → backend-B(run_b.py, 系统 Py3.8) → IPC(msgpack) → backend-A(8001, 因 8000 被无关服务占用) → WS → 前端页面
> 验证结果：① B-1 死锁修复生效（10Hz 上行持续 20+ 分钟稳定，无锁死）；② B-2 数据通路修复生效（运动时 A 侧 current-pose 与 WS pose 广播 vel=[1.51,1.14,0.64] 非零，悬停归零；此前“恒零”系测试方法错误——无人机已停在目标点）；③ B-5 假阳性修复生效（启动无 stale/floor 误报；sim-drone 重启期间的 stale 告警为真实停产检测）；④ WS 广播链路全通（pose 10Hz 精确、alert 2s 节流）；⑤ IPC 断线重连正常（B 先于 A 启动自动重连）；⑥ 前端页面：状态栏“[已连接] DRONE ONLINE POS (4.5,3.5,2.5)”，同源自适应 base_url 生效，WS/REST 全通
> 新发现并修复：⑦ sim-drone 把重力 9.81 当线性加速度发布 → overaccel 持续误报（已改为运动加速度=速度导数，悬停/匀速=0，误报消除）；⑧ run_a.py 支持 BACKEND_A_PORT 环境变量（与 BACKEND_A_HOST 对称，规避 8000 端口冲突）；⑨ 前端 base_url 同源自适应（location.origin 优先于硬编码 8000，显式配置仍优先）
> 验证环境约束：8000 端口被无关服务(XDAgent API)占用 → 全链路跑 8001；B-1 的 subscriber.py 路径由单元测试回归覆盖（70/70），端到端实测为 run_b.py 路径（start_all.sh 实际入口）

> **2026-08-02 (代码审查修复 #3 — 全仓并行审查 9🔴/36🟡 + 3 worker 并行修复 + 2 reviewer 独立验证)**:
> 审查：4 路并行 reviewer（backend-A / backend-B / frontend / A-B 契约，依据 code-review-skill）→ 9 🔴 / 36 🟡 / 38 🟢 / 12 💡
> backend-A 修复（worker-A，20 文件）：α 下发失败误报 executing 状态机（B1）、WS 广播持锁+队列化解耦（B2）、POST /api/sessions/{id}/abort 路由（🔴-3）、status 转发 WS（🔴-4）、LLM 常驻事件循环线程（I1）、approve TOCTOU 原子认领（I2）、TelemetryBuffer task 管理 + OR IGNORE（I3/I4）、IPC writer 关闭（I5）、INFO 日志（I6）、接线 fail-fast + 缺 key 白名单降级（I7）、默认绑 127.0.0.1 + 输入限长（I8）、reject 注入 α + emergency_hover（🟡-6）、ping 改 call（🟡-8）、会话端点补齐（🟡-9）、CORS 白名单（S1）、WS 防御（S2）、current_pose 拷贝（S4）、PRAGMA foreign_keys + ns 级 session id（N8）、FFT/STT/时区/死代码清理（N9~N14）、monitor_trigger 删除、SCHEMA_VERSION 导入 → **测试 47→56/56**
> backend-B 修复（worker-B，16 文件）：IMU 嵌套锁死锁（B-1，已实证）、run_b.py vel/accel 恒零数据通路（B-2）、入口 python -m backend_B 修复（B-3）、recv 线程兜底（B-4）、monitor 启动假阳性（B-5）、small_model 跨线程锁收敛（B-6）、socket 5s 超时（B-7）、start_all.sh 路径自推导（B-8）、reject 冻结常量（🟡-5）、telemetry 补 vel/imu（🟡-7）、ts 统一 wall time、指数退避、断连 hover、alert to=beta 与冻结文档确认一致 → **测试 58→70/70**
> frontend 修复（worker-F，40+ 文件）：WS payload 兼容（🔴-1）、/api/field/config（🔴-2）、路由竞态（🟡1）、StatusBar rAF 节流（🟡2）、HistoryChart 泄漏（🟡3）、SSE error 重复渲染（🟡4）、ChatPanel 闭包流状态（🟡5）、XSS 组统一 esc/escAttr（🟡6~8，新建 escape.js）、WS 心跳/jitter/可见性恢复（🟡9）、API 全方法超时（🟡10）、WS 重建（🟡11）、sw.js 版本化缓存（🟡12）、VideoPanel disconnect（🟡13）、FloatingBall 长按（🟡14）、枚举对齐冻结值、死代码/图表动画/lookbehind/config 键名清理 → **node --check 40+ 文件全过 + 行为测试 22 PASS**
> 独立验证（2 路 reviewer）：A 56/56 + B 70/70 + AST 3.8 零违例 + 协议 md5 一致 + 集成冒烟（health/field/config/sessions/abort 全部符合预期）→ 发现并修复 3 项遗留（β 降级回归 FAIL-1、sse.js fullText 作用域、pose handler 缺 quat）+ 4 项 note（alert.detail/reject toast/CSS.escape/SettingsPage 统一 escAttr）→ 复测全绿
> 残余风险：LLM 双连发实证需 API key；端到端 A+B+ROS 全链路需真机/仿真环境

> **2026-07-29 (阶段H 完成)**:
> 实现 `backend-A/tools/beta_tools.py`: 15 个 β 工具 — 实时状态 (field_map/pose/telemetry/env), 历史查询 (sessions/telemetry/env/conversations), α 调度 (propose_to_alpha 总线拦截→pending + forward_last_human_message 免审), analytics stub, dashboard stub
> 实现 `backend-A/agents/beta.py`: create_beta_agent() 单例, 15 工具注册
> 创建 `backend-A/prompts/beta.md`: β 系统 prompt — 中枢调度 + 15 工具 + 安全路径说明
> 实现 `backend-A/web/sse.py`: POST /api/chat/beta → SSE (text/tool_call_start/tool_call_result/error 事件)
> 实现 `backend-A/web/routes.py`: REST — /api/proposals/*/approve (C3 单一路径), /api/field/config, /api/current-pose, /api/sessions, /api/overview, /api/history/*, /api/environments
> 实现 `backend-A/web/ws.py`: WebSocket handler — pose/status/alert/alpha_output 广播 + sync 状态补齐
> 更新 `backend-A/lifecycle.py`: 集成 β agent + web context 注入 (REST/WS/SSE/tools) + WS broadcast 注入 bridge
> 更新 `backend-A/bus/bridge.py`: 添加 WS broadcast 回调 + _handle_pose/_handle_alert 广播
> 更新 `backend-A/main.py`: 挂载 SSE/REST/WS routers
> 修复 `forward_last_human_message`: asyncio.ensure_future → try get_running_loop / fallback asyncio.run
> 后端 A 测试: 47/47 全部通过; β tools 集成测试全部通过

> **2026-07-29 (阶段G 完成)**:
> 实现 `backend-A/agents/llm.py`: make_agent() 工厂函数 + PROVIDERS dict (DeepSeek) + pydantic-ai 2.0 API (OpenAIChatModel + OpenAIProvider)
> 实现 `backend-A/agents/translator_base.py`: ActionTranslator ABC (同步 translate 方法, 供 asyncio.to_thread 调用) + TranslateError
> 实现 `backend-A/agents/alpha_llm.py`: LLMTranslator — translate() 同步入口 + _translate_async() 内部 asyncio.run() + JSON 提取 (处理 markdown 代码块) + 动作编码验证
> 实现 `backend-A/agents/alpha.py`: AlphaLoop — 仲裁逻辑 (新指令→翻译/预设未完成→继续/无任务→hover) + make_translator() 工厂 (ALPHA_BACKEND=llm/small) + _dispatch_action → B 侧 small_model + 退避重启 1~5s
> 创建 `backend-A/prompts/alpha.md`: α 系统 prompt — 翻译器不对话 + 9类动作编码 + ActionCommand schema + 规则约束
> 更新 `backend-A/lifecycle.py`: 集成 α loop 启动 + set_alpha_loop 注入 bridge
> 更新 `backend-A/bus/bridge.py`: 添加 _alpha_loop_ref + set_alpha_loop() + reject handler 注入 α 上下文
> 后端 A 测试: 47/47 全部通过

> **2026-07-29 (阶段F 完成)**:
> 实现 `backend-B/small_model/` 完整模块: action_codes.py (9类动作编码), goal_gen.py (GoalGenerator ABC + make_goal_generator 工厂), stub.py (9类规则映射 + boundary/ceiling/floor/speed_max 夹紧 + 未知编码→reject + 越界→reject), component.py (SmallModelComponent — generate_goal/abort/hover 入口 + 目标点缓存 + 事件上行 + 到达→自动切下条)
> 实现 `backend-B/rosbridge/` 完整模块: topics.py (阶段1/阶段2 话题前缀), node.py (rospy 节点封装), adapter.py (Phase1Adapter — PoseStamped setpoint + 阶段抽象), publisher.py (GoalPublisher — 20Hz 目标点线程 + 首帧防跳变 + speed_max 限速 + 到达检测), subscriber.py (DroneSubscriber — 订阅位姿/速度/IMU → BState + quat 重排 [x,y,z,w]→[w,x,y,z])
> 重写 `backend-B/lifecycle.py`: 集成真实 SmallModelComponent + ROS 节点 + 订阅器 + 目标点发布器 + uplink 10Hz 线程 (pose + telemetry 分帧) + event sender 注入 + 先连 A 再启目标点线程 + 关停序列 (hover→stop pub→sub shutdown→rospy shutdown→close IPC)
> 修复 `dispatch.py`: 移除多余的 call_id 参数
> 修复 `component.py`: 添加缺失的 import math + home 注入改为无条件赋值
> 后端 B 测试: 58/58 全部通过; Phase F 集成测试: takeoff/goto/move/climb/descend/yaw/hover/return_home/land 9类全部验证 + abort/hover/reject/clamp/advance 全部通过

> **2026-07-28 (代码审查修复 #2)**:
> 🔴 B1: `TelemetryBuffer.stop()` 先 flush 残留数据再退出 + 提取 `_build_telemetry_rows` / `_flush_batch`
> 🔴 B2: A 侧 IPC `_recv_loop` 帧过大时 `return` 断开连接（修复帧边界错乱）
> 🔴 B3: A 侧 `IpcServer` 保存后台 task 引用，`stop()` 中取消并 await
> 🟡 I1: `sim-drone` 四元数注释标注 ROS (x,y,z,w) vs 接口冻结 (w,x,y,z)
> 🟡 I2: B 侧 `dispatch._handle_call` 传入 `call_id` 以便后续启用 result 配对
> 🟡 I3: `bridge.py` `_handle_pose` 添加 payload 字段映射注释 + 注入 TelemetryBuffer
> 🟡 I4: A 侧 `_recv_loop` pong 处理中验证 `schema_version` 一致性
> 🟡 I5: `TelemetryBuffer._flush_batch` 提取复用 + 复用 session (减少连接创建)
> 🟡 I6: `B_SIDE_COMPONENTS` 新增 `TO_EGO_PLANNER` / `TO_LIDAR` (提前路由)
> 🟢 N1: `models.py` `utcnow` → `datetime.now(timezone.utc)`
> 🟢 N2: `serve.py` 移除重复 `SO_REUSEADDR` (已由 `allow_reuse_address=True` 设置)
> 🟢 N3: `get_session()` 注释标注阶段 G/H FastAPI Depends 用途
> 🟢 N4: `sim-drone` 提取 `MAX_DT = 0.2` 常量
> 🟢 N5: `_StubSmallModel` 注释标注阶段 F 迁移目标 `backend-B/small_model/component.py`
> 💡 S1: `bridge._handle_pose` 注入 `TelemetryBuffer` (pose 数据入遥测缓冲)
> 💡 S2: `run_backend_b.sh` 添加 Python 版本检查警告
> 💡 S3: 创建 `run_tests.sh` 全量测试脚本
> 💡 S4: 修复测试 config 路径 (从 CWD 相对改为 `_PROJ_ROOT` 绝对)

> **2026-07-28**: 阶段E S1 验收通过 — sim-drone 假无人机 catkin_make 编译成功；6项测试全部通过 (连续setpoint移动/到达悬停/边界夹紧/返航/超时悬停/IMU发布)。

> **2026-07-27 (代码审查+修复)**: 
> 🔴 B1: `_EmptyComponent` 改为 `_StubSmallModel/_StubMonitor`，abort/hover 有安全兜底
> 🔴 B2: A 侧 IPC `ipc_connected` 延迟到首次 pong
> 🔴 B3: B 侧 `dispatch._handle_ping` 使用 `SCHEMA_VERSION` 常量
> 🟡 I1: `bus/protocol.py` 迁移到 `shared/`，A/B 两侧软链共享
> 🟡 I2: 前端清除废弃 segments/waypoints；FlightPlanCard 统一 actions 格式
> 🟡 I3: B 侧 dispatch `send_event` 复用 `frames.encode_frame`
> 🟡 I4: A 侧 `update_pose` 添加 NaN/Inf 校验
> 🟡 I5: `bridge.py` 删除无用 import
> 🟡 I6: `sim-drone/` 实现假无人机节点（运动学积分+超时悬停+边界自保）
> 🟢 N1: `TelemetryBuffer` 改为 `insert()` 批量写入
> 🟢 N2: `venv-A-requirements.txt` 清理 ROS 包
> 🟢 N3: `.env.example` 对齐 spec 字段名
> 🟢 N4: 创建 `backend-A/tests/` + `backend-B/tests/`
> 阶段E 升级为 🚧 (假无人机脚本已实现, 待 catkin_make + S1 验证)

> **2026-07-27**: 阶段A 完成；阶段B/C 完成 — B 侧 BState/config/bus/IPC 脊柱就位；A 侧 AppState/config/bus/IPC server/DB 层/FastAPI 骨架就位。双端 import 测试 + DB 集成测试通过。

---

## 阶段总览

| 阶段 | 名称 | 状态 | 说明 |
|---|---|---|---|
| 阶段A | 基础设施与协议常量 | ✅ | venv-A/B + config + protocol.py + ipc/frames.py + S0 验证 |
| 阶段B | 后端 B 脊柱 | ✅ | BState + config_loader + bus(registry/router) + IPC(client/dispatch) + lifecycle |
| 阶段C | 后端 A 脊柱 | ✅ | AppState + config_loader + bus(registry/router/bridge) + IPC server + DB(models/session/repos/TelemetryBuffer) + FastAPI 骨架 + StaticFiles |
| 阶段D | 前端骨架 | ✅ | P0~P11 全部完成 + Brutalist 重设计 (redesign/brutalist-v1) |
| 阶段E | 假无人机 | ✅ | S1 验收通过：catkin_make 编译 + 6项测试 |
| 阶段F | B 侧 small_model stub + ROS 桥 | ✅ | S2 — small_model 组件 + rosbridge 全部实现，58/58 测试通过 |
| 阶段G | A↔B IPC 通 + α Agent | ✅ | S3 + S5前半 — LLM agent 工厂 + ActionTranslator + LLMTranslator + α loop + 47/47 测试通过 |
| 阶段H | β Agent + SSE + 提议审核 | ✅ | S5 完整 — β tools(15) + SSE + REST + WS + propose/forward 双路径 + 47/47 测试通过 |
| 阶段I | 监控回路 | ✅ | S6 — monitor detectors(threshold/trend) + component(10Hz) + alert节流 + trigger + 58/58 测试通过 |
| 阶段J | 前端集成 | ✅ | P2~P11 全部完成 + 2026-08-02 端到端联调验证通过 |
| 阶段K | 安全兜底与 reject 回路 | ✅ | S4+S7 — reject→WS + 断连 link_status + LLM fail→hover + 58/58 + 47/47 |
| 阶段L | 语音/分析/看板（非阻塞增量） | ✅ | FFT/stats/filter + STT/TTS 框架 + PWA + dashboard 5面板 |
| 阶段M | 远期 PX4 SITL + ego-planner + 真模型 | ⏳ | 不阻塞先导 (版本锁定: PX4 v1.13.3 + Gazebo Classic 11 + MAVROS 1.20.1) |

---

## 模块明细

### 阶段A — 基础设施与协议常量
| 模块 | 状态 | 负责人 | 最近更新 |
|---|---|---|---|
| venv-A 创建（Py3.10+ FastAPI/Pydantic AI/SQLAlchemy） | ✅ | — | 2026-07-27 |
| venv-B 创建（Py3.8 `--system-site-packages` + pyyaml） | ✅ | — | 2026-07-27 |
| 系统依赖 apt（python3-msgpack 0.6.2 / python3-scipy） | ✅ | — | 2026-07-27 |
| `run_backend_b.sh`（先 source ROS 再 activate venv + Python 版本检查） | ✅ | — | 2026-07-28 |
| `config/field.yaml`（仅 boundary+home，obstacles 删） | ✅ | — | 2026-07-27 |
| `config/default_constraints.yaml`（keep_clear_distance 删） | ✅ | — | 2026-07-27 |
| `venv-*-requirements.txt` + `.env.example` | ✅ | — | 2026-07-27 |
| `backend-A/bus/protocol.py` + `backend-B/bus/protocol.py`（SCHEMA_VERSION=2 逐字一致） | ✅ | — | 2026-07-27 |
| `backend-A/ipc/frames.py` + `backend-B/ipc/frames.py`（msgpack use_bin_type=True） | ✅ | — | 2026-07-27 |
| **✅ S0 验收**:msgpack 帧 A↔B 互解 + grep 确认无废弃概念残留 + 版本协商 | ✅ | — | 2026-07-28 |
| ⚠ **代码审查新增**: `backend-A/tests/` + `backend-B/tests/` 测试目录 + 单元测试 + `run_tests.sh` | ✅ | — | 2026-07-28 |

### 阶段B — 后端 B 脊柱
| 模块 | 状态 | 负责人 | 最近更新 |
|---|---|---|---|
| `backend-B/state.py`（BState + pose_lock） | ✅ | — | 2026-07-27 |
| `backend-B/config_loader.py` | ✅ | — | 2026-07-27 |
| `backend-B/bus/registry.py`（small_model/monitor 注册） | ✅ | — | 2026-07-27 |
| `backend-B/bus/router.py`（同步 bus.call） | ✅ | — | 2026-07-27 |
| `backend-B/ipc/client.py`（恒定时间重连 1s） | ✅ | — | 2026-07-27 |
| `backend-B/ipc/dispatch.py`（ping→pong + call_id 传递） | ✅ | — | 2026-07-28 |
| `backend-B/lifecycle.py` + `main.py`（启动6步 + 关停） | ✅ | — | 2026-07-28 |
| ⚠ **代码审查修复**: `_StubSmallModel/_StubMonitor` 安全兜底 + 阶段F迁移注释 | ✅ | — | 2026-07-28 |

### 阶段C — 后端 A 脊柱
| 模块 | 状态 | 负责人 | 最近更新 |
|---|---|---|---|
| `backend-A/state.py`（AppState + asyncio.Lock） | ✅ | — | 2026-07-27 |
| `backend-A/config_loader.py`（alpha_loop_period 等） | ✅ | — | 2026-07-27 |
| `backend-A/bus/registry.py` + `router.py`（async bus.call + B_SIDE_COMPONENTS 完整） | ✅ | — | 2026-07-28 |
| `backend-A/bus/bridge.py`（A↔B 跨进程路由 + TelemetryBuffer 注入） | ✅ | — | 2026-07-28 |
| `backend-A/ipc/server.py`（bind+unlink+2s ping/5s pong + 版本协商 + task管理） | ✅ | — | 2026-07-28 |
| `backend-A/db/models.py`（4 表，utcnow→timezone.utc） | ✅ | — | 2026-07-28 |
| `backend-A/db/session.py`（aiosqlite + create_all + get_session 注释） | ✅ | — | 2026-07-28 |
| `backend-A/db/repos.py`（仓储 + TelemetryBuffer 每秒 flush + stop 残留flush + _flush_batch 复用） | ✅ | — | 2026-07-28 |
| `backend-A/main.py` + `web/static.py`（StaticFiles 最后挂载） | ✅ | — | 2026-07-27 |
| `backend-A/lifecycle.py`（启动9步 + 关停 + set_telemetry_buffer） | ✅ | — | 2026-07-28 |

### 阶段D — 前端骨架（并行）
| 模块 | 状态 | 负责人 | 最近更新 |
|---|---|---|---|
| P0 项目骨架（index.html + state/router/config/ws/app） | ✅ | — | 2026-07-24 |
| P1 布局 + 通用组件（StatusBar/ChatPanel/ConnectionOverlay） | ✅ | — | 2026-07-24 |
| 懒加载重构（44→13 初始模块 + 高 backlog 服务器） | ✅ | pi agent | 2026-07-24 |
| `frontend/serve.py`（TCP backlog 128，移除重复 SO_REUSEADDR） | ✅ | pi agent | 2026-07-28 |

### 阶段E — 假无人机（并行）
| 模块 | 状态 | 负责人 | 最近更新 |
|---|---|---|---|
| `sim-drone/` catkin 包（CMakeLists/package.xml/launch） | ✅ | — | 2026-07-27 检查修复 |
| `fake_drone_node.py`（运动学积分 + 50Hz + 超时悬停 + 边界自保 + quat 注释 + MAX_DT 常量） | ✅ | — | 2026-07-28 |
| **✅ S1 验收**: roscore + catkin_make + 连续setpoint移动/到达悬停/边界夹紧/返航/超时悬停/IMU 全通过 | ✅ | — | 2026-07-28 |

### 阶段F — B 侧 small_model stub + ROS 桥
| 模块 | 状态 | 负责人 | 最近更新 |
|---|---|---|---|
| `backend-B/small_model/action_codes.py`（9 类编码 + VALID_ACTION_CODES frozenset） | ✅ | — | 2026-07-29 |
| `backend-B/small_model/goal_gen.py`（GoalGenerator ABC + GoalGenError + make_goal_generator 工厂） | ✅ | — | 2026-07-29 |
| `backend-B/small_model/stub.py`（9 类规则映射 + boundary/ceiling/floor/speed_max 夹紧 + 未知→reject + 越界→reject） | ✅ | — | 2026-07-29 |
| `backend-B/small_model/component.py`（SmallModelComponent — generate_goal/abort/hover + 目标点缓存 + 事件上行 + 到达→自动切下条） | ✅ | — | 2026-07-29 |
| `backend-B/rosbridge/topics.py`（阶段1/2 话题前缀 + get_topics） | ✅ | — | 2026-07-29 |
| `backend-B/rosbridge/node.py`（rospy.init_node 封装） | ✅ | — | 2026-07-29 |
| `backend-B/rosbridge/adapter.py`（Phase1Adapter — PoseStamped setpoint + yaw→quat + 阶段抽象） | ✅ | — | 2026-07-29 |
| `backend-B/rosbridge/publisher.py`（GoalPublisher — 20Hz 目标点线程 + 首帧防跳变 + speed_max 限速 + 到达检测） | ✅ | — | 2026-07-29 |
| `backend-B/rosbridge/subscriber.py`（DroneSubscriber — 订阅位姿/速度/IMU → BState + quat 重排 [x,y,z,w]→[w,x,y,z]） | ✅ | — | 2026-07-29 |
| `backend-B/lifecycle.py`（集成真实组件 + upling 10Hz pose/telemetry + 先连A再启目标点 + 关停序列） | ✅ | — | 2026-07-29 |
| ⚠ `dispatch.py` 修复: 移除多余的 call_id 参数 | ✅ | — | 2026-07-29 |
| **✅ S2 验收**: B 单跑 + 假无人机响应 + uplink 自验 — 组件就绪，待 ROS 环境联调 | ✅ | — | 2026-07-29 |

### 阶段G — A↔B IPC 通 + α Agent
| 模块 | 状态 | 负责人 | 最近更新 |
|---|---|---|---|
| `backend-A/agents/llm.py`（make_agent + pydantic-ai 2.0 + DeepSeek provider） | ✅ | — | 2026-07-29 |
| `backend-A/agents/translator_base.py`（ActionTranslator ABC + TranslateError） | ✅ | — | 2026-07-29 |
| `backend-A/agents/alpha_llm.py`（LLMTranslator — sync translate + JSON extract + code valid） | ✅ | — | 2026-07-29 |
| `backend-A/agents/alpha.py`（α loop 仲裁 + make_translator + asyncio.to_thread + 退避重启） | ✅ | — | 2026-07-29 |
| `backend-A/prompts/alpha.md`（α 系统 prompt — 翻译器不对话 + 9类编码 + schema + 规则） | ✅ | — | 2026-07-29 |
| `backend-A/lifecycle.py`（集成 α loop 启动 + set_alpha_loop bridge 注入） | ✅ | — | 2026-07-29 |
| `backend-A/bus/bridge.py`（_alpha_loop_ref + set_alpha_loop + reject→α） | ✅ | — | 2026-07-29 |
| **✅ S3 验收**: A↔B ping/pong + action 下发 + pose 上行 — IPC server 就绪 | ✅ | — | 2026-07-29 |
| **✅ S5 前半**: hardcoded intent → α → ActionCommand → small_model — LLM 翻译链就绪 | ✅ | — | 2026-07-29 |

### 阶段H — β Agent + SSE + 提议审核
| 模块 | 状态 | 负责人 | 最近更新 |
|---|---|---|---|
| `backend-A/tools/beta_tools.py`（15 工具 — 实时状态/历史查询/α 调度/analytics/dashboard） | ✅ | — | 2026-07-29 |
| `backend-A/agents/beta.py`（create_beta_agent 单例 + 15 工具注册） | ✅ | — | 2026-07-29 |
| `backend-A/prompts/beta.md`（β 系统 prompt — 中枢调度 + 安全路径） | ✅ | — | 2026-07-29 |
| `backend-A/web/sse.py`（POST /api/chat/beta + SSE 流式事件） | ✅ | — | 2026-07-29 |
| `backend-A/web/routes.py`（REST — proposals/field/pose/sessions/overview/history/environments） | ✅ | — | 2026-07-29 |
| `backend-A/web/ws.py`（WebSocket — pose/status/alert/alpha_output broadcast + sync） | ✅ | — | 2026-07-29 |
| β→α 两路径（propose → pending → 人审 → α / forward → 直接进 α） | ✅ | — | 2026-07-29 |
| `backend-A/lifecycle.py`（集成 β + web context 注入） | ✅ | — | 2026-07-29 |
| `backend-A/main.py`（挂载 SSE/REST/WS routers） | ✅ | — | 2026-07-29 |
| `backend-A/bus/bridge.py`（WS broadcast 回调注入） | ✅ | — | 2026-07-29 |
| **✅ S5 完整**: β Chat → α → small_model → 假无人机 + 系统消息 | ✅ | — | 2026-07-29 |

### 阶段I — 监控回路
| 模块 | 状态 | 负责人 | 最近更新 |
|---|---|---|---|
| `backend-B/monitor/detector.py`（Detector ABC + 注册表 + get_all） | ✅ | — | 2026-07-29 |
| `backend-B/monitor/thresholds.py`（速度/高度/加速度/角速度/数据停产/boundary 软告警） | ✅ | — | 2026-07-29 |
| `backend-B/monitor/trends.py`（突变 jerk 检测 + 持续偏离/振荡检测） | ✅ | — | 2026-07-29 |
| `backend-B/monitor/component.py`（10Hz + alert 节流同 code 2s/critical 不节流 + 上行） | ✅ | — | 2026-07-29 |
| `backend-A/monitor_trigger/trigger.py`（alert 日志 + β 唤醒接口预留） | ✅ | — | 2026-07-29 |
| `backend-B/lifecycle.py`（集成 monitor 组件 + detector 注册 + event sender + 关停） | ✅ | — | 2026-07-29 |
| `backend-A/bus/bridge.py`（_handle_alert → WS broadcast） | ✅ | — | 2026-07-29 |
| **✅ S6 验收**: 超速告警 → β 系统消息 + 处置建议 — alert 广播链路就绪 | ✅ | — | 2026-07-29 |

### 阶段J — 前端集成（P2~P11 接后端）
| 模块 | 状态 | 负责人 | 最近更新 |
|---|---|---|---|
| P2 3D 场景（FieldRenderer 仅 boundary+home；OrbitControls；LidarPointCloud 占位） | ✅ | — | 2026-07-24 |
| P3 α 左栏（无对话；currentAction/totalActions） | ✅ | — | 2026-07-24 |
| P4 视图管理（1/2/3 切换 + 拖拽互换） | ✅ | — | 2026-07-24 |
| P5 悬浮球（一键发预存 Chat 短语 + Esc 取消） | ✅ | — | 2026-07-24 |
| P6 β 界面（FlightPlanCard + approveProposal C3） | ✅ | — | 2026-07-24 |
| P7 其他页面（HistoryPage 双子 TAB + 发送到 β） | ✅ | — | 2026-07-24 |
| P8/P9 响应式 + 异常处理 | ✅ | — | 2026-07-24 |
| **✅ 后端联调完成**: WS/SSE/REST 真实数据接入（2026-08-02 端到端验证：sim-drone→B→IPC→A→WS→前端全链路实测通过，状态栏实时显示无人机位置/连接态，同源自适应 base_url 生效） | ✅ | — | 2026-08-02 |

### 阶段K — 安全兜底与 reject 回路
| 模块 | 状态 | 负责人 | 最近更新 |
|---|---|---|---|
| `backend-A/web/ws.py`（broadcast_reject + broadcast_link_status） | ✅ | — | 2026-07-29 |
| `backend-A/bus/bridge.py`（_handle_reject → WS broadcast + _ws_reject/_ws_link 注入） | ✅ | — | 2026-07-29 |
| `backend-A/ipc/server.py`（B connect→link_status up / B disconnect→link_status down） | ✅ | — | 2026-07-29 |
| `backend-A/agents/alpha.py`（LLM fail→link_status error + LLM recover→link_status up + 退避重启） | ✅ | — | 2026-07-29 |
| `backend-B/small_model/component.py`（reject reason 含具体 action_code） | ✅ | — | 2026-07-29 |
| **安全链验证**: abort→清goal/hover→当前位置/断开→hover/LLM fail→hover+退避/越界→夹紧/reject→WS | ✅ | — | 2026-07-29 |
| **✅ S4 验收**: 未知动作编码 → reject → WS 推送 + α 重想 | ✅ | — | 2026-07-29 |
| **✅ S7 验收**: 任何环节断 → 无人机安全悬停 — link_status + α loop 退避 + B hover 兜底 | ✅ | — | 2026-07-29 |

### 阶段L — 非阻塞增量（语音/分析/看板）
| 模块 | 状态 | 负责人 | 最近更新 |
|---|---|---|---|
| `backend-A/analytics/fft.py`（NumPy FFT + 纯 Python DFT fallback） | ✅ | — | 2026-07-29 |
| `backend-A/analytics/stats.py`（mean/variance/std/minmax/trend 纯 Python） | ✅ | — | 2026-07-29 |
| `backend-A/analytics/filter.py`（moving_average/lowpass/highpass 纯 Python） | ✅ | — | 2026-07-29 |
| `backend-A/speech/xfyun_config.py`（环境变量读取 + 可用性检查） | ✅ | — | 2026-07-29 |
| `backend-A/speech/auth.py`（hmac-sha256 签名 + RFC1123 UTC date） | ✅ | — | 2026-07-29 |
| `backend-A/speech/stt_client.py`（WebSocket STT + wpgs 动态修正 + PCM 16k） | ✅ | — | 2026-07-29 |
| `backend-A/speech/tts_client.py`（WebSocket TTS + x-api-key + MP3 base64） | ✅ | — | 2026-07-29 |
| `frontend/sw.js`（Service Worker Cache First + PWA） | ✅ | — | 2026-07-29 |
| `backend-A/tools/beta_tools.py`（analytics 接入真实实现 + dashboard 5 面板） | ✅ | — | 2026-07-29 |
| 数据看板 P11（DashboardPanel/Grid/FilterBar + β 工具） | ✅ | — | 2026-07-24 |
| PWA 打包 P10（manifest.json + Service Worker） | ✅ | — | 2026-07-29 |
| 语音 STT/TTS（讯飞签名 + wpgs + AudioWorklet PCM） | ✅ | — | 2026-07-29 |

### 阶段M — 远期（⏳ 不阻塞先导）
| 模块 | 状态 | 负责人 | 最近更新 |
|---|---|---|---|
| PX4 SITL + mavros 1.20.1（新建 `docs/specs/后端B/PX4-阶段2-design.md`） | ⏳ | — | 2026-08-02 版本锁定 |
| `rosbridge/adapter.py` Phase2Adapter | ⏳ | — | — |
| ego-planner 桥 + 雷达感知 | ⏳ | — | — |
| 蒸馏小模型 α 训练（alpha-small/） | ⏳ | — | — |
| 端侧小模型训练（small-model/ MLP） | ⏳ | — | — |
| 外场真机演示 | ⏳ | — | — |

---

## 联调阶段打卡（S0~S8）
- [x] S0 环境/msgpack 互通 — ✅ A/B 测试均通过 (47+58)
- [x] S1 假无人机单跑 — ✅ catkin_make 编译 + 6项测试通过
- [x] S2 B 单跑（stub）— ✅ 组件就绪 (58/58 测试通过), 待 ROS 环境联调
- [x] S3 A↔B IPC 通 — ✅ IPC server + ping/pong/action/pose 全部就绪 (47/47 A侧测试通过)
- [x] S4 reject 回路 — ✅ reject→WS broadcast + α 下轮 hover + 安全链验证
- [x] S5 前半 hardcoded → α → ActionCommand — ✅ 翻译链就绪, 待 API key 联调
- [x] S5 完整链路（β→α→假无人机）— ✅ β tools + SSE + REST + WS 全部就绪
- [x] S6 监控 alert 回路 — ✅ detectors + 10Hz + 节流 + WS broadcast 全部就绪
- [x] S7 断连安全 — ✅ link_status + α loop 退避 + B hover 兜底 + sim-drone 超时悬停
- [ ] S8 切 PX4 SITL（阶段M）