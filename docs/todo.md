# 试飞控制系统 — 模块进度

> 本文件是**模块级进度追踪**，对齐 [`docs/开发规划.md`](开发规划.md) 的阶段 A~M。
> 规则见 [`CLAUDE.md`](../CLAUDE.md) §四：每模块完成时更新此文件 + todo 插件 + git push；开发前先 git pull。
> 状态图例：⬜ 未开始 / 🚧 进行中 / ✅ 已完成 / ⏳ 远期

最近更新：2026-07-23

---

## 阶段总览

| 阶段 | 名称 | 状态 | 说明 |
|---|---|---|---|
| 阶段A | 基础设施与协议常量 | ⬜ | venv-A/B + config + bus/protocol + S0 |
| 阶段B | 后端 B 脊柱 | ⬜ | bus + IPC client + BState |
| 阶段C | 后端 A 脊柱 | ⬜ | bus + IPC server + AppState + DB |
| 阶段D | 前端骨架 | ⬜ | P0~P1 |
| 阶段E | 假无人机 | ⬜ | sim-drone catkin 包 |
| 阶段F | B 侧 small_model stub + ROS 桥 | ⬜ | S2 |
| 阶段G | A↔B IPC 通 + α Agent | ⬜ | S3 + S5 前半 |
| 阶段H | β Agent + SSE + 提议审核 | ⬜ | S5 完整 |
| 阶段I | 监控回路 | ⬜ | S6 |
| 阶段J | 前端集成 | ⬜ | P2~P11 接后端 |
| 阶段K | 安全兜底与 reject 回路 | ⬜ | S4 + S7 |
| 阶段L | 语音/分析/看板（非阻塞增量） | ⬜ | 讯飞 STT/TTS + analytics + 看板 |
| 阶段M | 远期 PX4 SITL + ego-planner + 真模型 | ⏳ | 不阻塞先导 |

---

## 模块明细

### 阶段A — 基础设施与协议常量
| 模块 | 状态 | 负责人 | 最近更新 |
|---|---|---|---|
| venv-A 创建（Py3.10+ FastAPI/Pydantic AI/SQLAlchemy） | ⬜ | — | — |
| venv-B 创建（Py3.8 `--system-site-packages` + pyyaml） | ⬜ | — | — |
| 系统依赖 apt（python3-msgpack 0.6.2 / python3-scipy） | ⬜ | — | — |
| `run_backend_b.sh`（先 source ROS 再 activate venv） | ⬜ | — | — |
| `config/field.yaml`（仅 boundary+home，obstacles 删） | ⬜ | — | — |
| `config/default_constraints.yaml`（keep_clear_distance 删） | ⬜ | — | — |
| `venv-*-requirements.txt` + `.env.example` | ⬜ | — | — |
| `backend-A/bus/protocol.py` + `backend-B/bus/protocol.py`（SCHEMA_VERSION=2 逐字一致） | ⬜ | — | — |
| `backend-A/ipc/frames.py` + `backend-B/ipc/frames.py`（msgpack use_bin_type=True） | ⬜ | — | — |
| **✅ S0 验收**:msgpack 帧 A↔B 互解 + grep 确认无废弃概念残留 | ⬜ | — | — |

### 阶段B — 后端 B 脊柱
| 模块 | 状态 | 负责人 | 最近更新 |
|---|---|---|---|
| `backend-B/state.py`（BState + pose_lock） | ⬜ | — | — |
| `backend-B/config_loader.py` | ⬜ | — | — |
| `backend-B/bus/registry.py`（small_model/monitor 注册） | ⬜ | — | — |
| `backend-B/bus/router.py`（同步 bus.call） | ⬜ | — | — |
| `backend-B/ipc/client.py`（恒定时间重连 1s） | ⬜ | — | — |
| `backend-B/ipc/dispatch.py`（ping→pong） | ⬜ | — | — |

### 阶段C — 后端 A 脊柱
| 模块 | 状态 | 负责人 | 最近更新 |
|---|---|---|---|
| `backend-A/state.py`（AppState + asyncio.Lock） | ⬜ | — | — |
| `backend-A/config_loader.py`（alpha_loop_period 等） | ⬜ | — | — |
| `backend-A/bus/registry.py` + `router.py`（async bus.call） | ⬜ | — | — |
| `backend-A/bus/bridge.py`（A↔B 跨进程路由） | ⬜ | — | — |
| `backend-A/ipc/server.py`（bind+unlink+2s ping/5s pong） | ⬜ | — | — |
| `backend-A/db/models.py`（4 表，alpha_actions 非 alpha_trajectory） | ⬜ | — | — |
| `backend-A/db/session.py`（aiosqlite + create_all） | ⬜ | — | — |
| `backend-A/db/repos.py`（仓储 + TelemetryBuffer 每秒 flush） | ⬜ | — | — |
| `backend-A/main.py` + `web/static.py`（StaticFiles 最后挂载） | ⬜ | — | — |

### 阶段D — 前端骨架（并行）
| 模块 | 状态 | 负责人 | 最近更新 |
|---|---|---|---|
| P0 项目骨架（index.html + state/router/config/ws/app） | ⬜ | — | — |
| P1 布局 + 通用组件（StatusBar/ChatPanel/ConnectionOverlay） | ⬜ | — | — |

### 阶段E — 假无人机（并行）
| 模块 | 状态 | 负责人 | 最近更新 |
|---|---|---|---|
| `sim-drone/` catkin 包（CMakeLists/package.xml/launch） | ⬜ | — | — |
| `fake_drone_node.py`（运动学积分 + 50Hz 发布 + 超时悬停 + 边界自保） | ⬜ | — | — |
| **✅ S1 验收**:roscore + 手动 pub setpoint → 移动+回传+超时悬停 | ⬜ | — | — |

### 阶段F — B 侧 small_model stub + ROS 桥
| 模块 | 状态 | 负责人 | 最近更新 |
|---|---|---|---|
| `backend-B/small_model/action_codes.py`（9 类编码） | ⬜ | — | — |
| `backend-B/small_model/goal_gen.py`（GoalGenerator ABC + 路由） | ⬜ | — | — |
| `backend-B/small_model/stub.py`（9 类规则映射 + 夹紧 + 未知→reject） | ⬜ | — | — |
| `backend-B/small_model/component.py`（generate_goal/abort/hover） | ⬜ | — | — |
| `backend-B/rosbridge/topics.py` + `node.py` + `publisher.py`（首帧填当前位置） + `subscriber.py` + `adapter.py`(Phase1) | ⬜ | — | — |
| `backend-B/lifecycle.py` + `main.py`（先连 A 再启目标点线程；threading 不引入 asyncio） | ⬜ | — | — |
| **✅ S2 验收**:B 单跑 + 假无人机响应 + uplink 自验 | ⬜ | — | — |

### 阶段G — A↔B IPC 通 + α Agent
| 模块 | 状态 | 负责人 | 最近更新 |
|---|---|---|---|
| **✅ S3 验收**:A↔B ping/pong + action 下发 + pose 上行 | ⬜ | — | — |
| `backend-A/agents/llm.py`（make_agent + deepseek provider） | ⬜ | — | — |
| `backend-A/agents/translator_base.py`（ActionTranslator ABC） | ⬜ | — | — |
| `backend-A/agents/alpha_llm.py`（LLMTranslator） | ⬜ | — | — |
| `backend-A/agents/alpha.py`（α loop + asyncio.to_thread 非阻塞） | ⬜ | — | — |
| `backend-A/prompts/alpha.md` | ⬜ | — | — |
| `run_agent_with_log` 带 `metadata.approved/path/action_code` | ⬜ | — | — |
| **✅ S5 前半**:hardcoded intent → α → ActionCommand → 假无人机 | ⬜ | — | — |

### 阶段H — β Agent + SSE + 提议审核
| 模块 | 状态 | 负责人 | 最近更新 |
|---|---|---|---|
| `backend-A/agents/beta.py` + `tools/beta_tools.py`（最小集） + `prompts/beta.md` | ⬜ | — | — |
| `backend-A/web/sse.py`（POST /api/chat/beta + SSE 事件） | ⬜ | — | — |
| `backend-A/web/routes.py`（/api/proposals/*/approve，C3 单一路径） | ⬜ | — | — |
| `backend-A/web/ws.py`（下行 pose/status/reject/alert/alpha_output/...） | ⬜ | — | — |
| β→α 两路径（propose 总线层拦截 / forward 免审） | ⬜ | — | — |
| **✅ S5 完整**:β Chat → α → 假无人机 + 系统消息 | ⬜ | — | — |

### 阶段I — 监控回路
| 模块 | 状态 | 负责人 | 最近更新 |
|---|---|---|---|
| `backend-B/monitor/detector.py`（Detector ABC + 注册表） | ⬜ | — | — |
| `backend-B/monitor/thresholds.py`（位置超 boundary 软告警） | ⬜ | — | — |
| `backend-B/monitor/trends.py`（突变/持续偏离） | ⬜ | — | — |
| `backend-B/monitor/component.py`（10Hz + 节流） | ⬜ | — | — |
| `backend-A/monitor_trigger/trigger.py`（WS alert + 唤醒 β） | ⬜ | — | — |
| **✅ S6 验收**:超速告警 → β 系统消息 + 处置建议 | ⬜ | — | — |

### 阶段J — 前端集成（P2~P11 接后端）
| 模块 | 状态 | 负责人 | 最近更新 |
|---|---|---|---|
| P2 3D 场景（FieldRenderer 仅 boundary+home；OrbitControls） | ⬜ | — | — |
| P3 α 左栏（无对话；currentAction/totalActions） | ⬜ | — | — |
| P4 视图管理（1/2/3 切换 + 拖拽互换） | ⬜ | — | — |
| P5 悬浮球（一键发预存 Chat 短语） | ⬜ | — | — |
| P6 β 界面（FlightPlanCard + approveProposal C3） | ⬜ | — | — |
| P7 其他页面（HistoryPage 双子 TAB + 发送到 β） | ⬜ | — | — |
| P8/P9 响应式 + 异常处理 | ⬜ | — | — |

### 阶段K — 安全兜底与 reject 回路
| 模块 | 状态 | 负责人 | 最近更新 |
|---|---|---|---|
| **✅ S4 验收**:未知动作编码 → reject → α 重想 | ⬜ | — | — |
| **✅ S7 验收**:杀 A/B → 无人机安全悬停 | ⬜ | — | — |

### 阶段L — 非阻塞增量（语音/分析/看板）
| 模块 | 状态 | 负责人 | 最近更新 |
|---|---|---|---|
| 语音 STT/TTS（讯飞签名 + wpgs + AudioWorklet PCM） | ⬜ | — | — |
| analytics 工具（fft/stats/filter） | ⬜ | — | — |
| 数据看板 P11（DashboardPanel/Grid/FilterBar + β 工具） | ⬜ | — | — |
| PWA 打包 P10（manifest + Service Worker） | ⬜ | — | — |

### 阶段M — 远期（⏳ 不阻塞先导）
| 模块 | 状态 | 负责人 | 最近更新 |
|---|---|---|---|
| PX4 SITL + mavros 1.20.1（待写 PX4-阶段2-design.md） | ⏳ | — | — |
| `rosbridge/adapter.py` Phase2Adapter | ⏳ | — | — |
| ego-planner 桥 + 雷达感知 | ⏳ | — | — |
| 蒸馏小模型 α 训练（alpha-small/） | ⏳ | — | — |
| 端侧小模型训练（small-model/ MLP） | ⏳ | — | — |
| 外场真机演示 | ⏳ | — | — |

---

## 联调阶段打卡（S0~S8）
- [ ] S0 环境/msgpack 互通
- [ ] S1 假无人机单跑
- [ ] S2 B 单跑（stub）
- [ ] S3 A↔B IPC 通
- [ ] S4 reject 回路
- [ ] S5 完整链路（β→α→假无人机）
- [ ] S6 监控 alert 回路
- [ ] S7 断连安全
- [ ] S8 切 PX4 SITL（阶段M）