# 项目工作约定

> 本文件是本仓库 Agent 与人类协作者的**工作约定总纲**。
> **优先级声明**：本文件的「文档整理与阅读规则」优先级**高于**任何历史"superpowers"工作流约定（含旧的 `docs/superpowers/` 目录命名与流程约定）。若冲突，一律以本文件为准。

---

## 一、工具使用

- **不要使用 WebSearch**：该功能在本环境不可用，调用会失败。
- **改用 context7**：涉及任何库、框架、SDK、API、CLI 工具时，用 context7 MCP 工具（`mcp__plugin_context7_context7__resolve-library-id` 解析库 ID，再 `mcp__plugin_context7_context7__query-docs` 拉取当前文档与代码示例）获取准确信息，而非凭记忆作答。
- WebFetch 仅在必要时使用（且目标 URL 已知可达时）。

---

## 二、开发环境

- 详细环境与版本锁定见 [`docs/specs/总体/2026-07-01-总体架构-design.md`](docs/specs/总体/2026-07-01-总体架构-design.md) §4。
- ROS1 Noetic 锁定 Python 3.8；AI/agent 相关库要求 Python 3.10+，需双虚拟环境（venv-A Py3.10+ / venv-B Py3.8），仅经 Unix socket 通信（见总体架构 spec §4.1）。
- 主机：WSL2 Ubuntu 20.04 + Windows 11，mirrored 网络模式。

---

## 三、文档整理与阅读规则（优先级高于 superpowers）

> 本节为 2026-07-23 文档整理后确立的**现行规则**，取代一切旧的 superpowers 文档约定。

### 3.1 目录结构与用途分类

```
docs/
├── 设计目标.md            # 研究目标与背景（需求背景，非设计权威）
├── 开发规划.md            # 阶段 A~M 执行计划与排期（落地开发路径）
├── todo.md                # 模块级进度追踪（各模块状态，对齐 开发规划.md）
├── specs/                 # ★ 权威设计文档（唯一设计权威）
│   ├── README.md          # 索引与阅读顺序
│   ├── 总体/              # 跨子系统契约与顶层设计
│   ├── 后端A/             # Agent 中枢 spec
│   ├── 后端B/             # 飞控桥 spec
│   └── 前端/              # 前端 spec
└── 过时存档/               # 已过时文档（优先级最低，仅历史追溯）
    ├── README.md
    ├── 手写设计稿/         # 原始需求 prompt
    ├── 过程文件/           # 重构执行记录/审查报告
    ├── 架构概要.md
    ├── 试飞控制系统技术报告.md
    ├── generate_images.py
    └── report_images/
```

### 3.2 文档优先级（冲突仲裁）

从高到低，**高优先级覆盖低优先级**：

1. **`docs/specs/`** — 唯一设计权威。编码与决策的唯一依据。
2. **`docs/开发规划.md`** — 执行计划；与 spec 冲突时以 spec 为准。
3. **`docs/设计目标.md`** — 需求背景；仅作"为什么做"的参考，不作"怎么做"的依据。
4. **`docs/过时存档/`** — 优先级最低，**不作编码或决策依据**，仅供历史追溯。

> 任何文档与本规则冲突时，按上述优先级仲裁；`过时存档/` 内容一律不作数。

### 3.3 阅读规则

- **动手编码前**：先读 `docs/specs/README.md` 的阅读顺序，再按职责读对应模块 spec。
- **新组件接入**：读 `docs/specs/总体/开放式接口规范.md`（接入手册）。
- **跨进程接口变更**：读 `docs/specs/总体/2026-07-05-A-B-接口冻结.md`，按 §9 变更控制升级 `schema_version` 并两侧同步。
- **查进度/排期**：读 `docs/开发规划.md`；阶段性进展记入 `docs/status.md`（见测试与质量路线图 §2 约定）。
- **`docs/过时存档/` 仅供背景**：其中的相对链接可能已失效，引用历史内容时回到 `docs/specs/` 查权威版本。

### 3.4 变更规则

- `docs/specs/` 下 spec 变更：**必须同步更新所有交叉引用**（specs 间链接按模块相对路径 `../<模块>/文件名.md`，同模块内直引文件名）。
- `docs/specs/总体/A-B-接口冻结.md` 字段级变更：必须升 `schema_version` 并同步 A/B 两侧 `bus/protocol.py` 常量，更新 §9 变更控制表。
- 新文档归位：设计类入 `docs/specs/<模块>/`；进度类入 `docs/`（如 `status.md`）；归档类入 `docs/过时存档/` 并在 `过时存档/README.md` 登记过时原因与权威替代。
- **废弃概念全仓不应残留**：`TrajectorySpec` / `solver` / `FlightPlanSegment` / `segmentIndex` / `waypoints` / `alpha_trajectory` / `/api/plan/approve` / `keep_clear_distance` / `obstacles` 预编 / `superpowers/specs` 旧路径——出现即按现行设计修正。
- 当前协议版本：`schema_version = 2`。

---

## 四、浏览器开发环境（pi agent 专用）

> [!NOTE] 本节仅供 pi agent 阅读。Claude Code / Cursor 等其他 agent 请忽略——它们有自己的浏览器工具链，与以下内容无关。

### 4.1 浏览器工具：BetterWright

前端开发与调试使用 **BetterWright**（v1.3.1），通过 pi 扩展注册 `browser` / `browser_login` / `browser_download` / `browser_evidence` 四个工具。

```bash
# 已安装为项目级 pi 扩展（.pi/settings.json）
pi install -l npm:betterwright
```

Chromium fork 位于 `~/.betterwright/chromium/linux-x64/chrome`，后台 daemon 通过 Unix socket 通信（`~/.betterwright/daemon.sock`）。

### 4.2 已知问题与解决

| 问题 | 现象 | 原因 | 解决 |
|------|------|------|------|
| **Chromium fork 下载 SSL 失败** | `betterwright setup` 报 `unable to verify the first certificate` | 系统代理 `127.0.0.1:7897` 拦截 SSL 证书 | 手动 curl 下载 zip 并解压到 `~/.betterwright/chromium/` |
| **Guard proxy 阻断 localhost** | `net::ERR_SOCKS_CONNECTION_FAILED` | BetterWright 内置 guard proxy (`socks5://127.0.0.1:43417`) 依赖前端服务存活；服务挂了代理就报错 | 确保 `python3 -m http.server` 在访问前已启动且监听 `0.0.0.0` |
| **Profile 锁冲突** | `Another BetterWright process owns the persistent browser profile` | 旧 daemon 未正常退出（`pkill` 残留或崩溃锁未过期） | `pkill -f betterwright` 后等待 1 分钟让锁自动过期 |
| **`npx serve` 不稳定** | `serve` 进程在 WSL 后台随机挂掉 | Node.js `serve` 包在 WSL 后台模式下不可靠 | 换用 `python3 -m http.server <port>` |

### 4.3 前端开发工作流

```bash
# 1. 启动前端静态服务（用 python3，比 npx serve 稳定）
cd frontend && python3 -m http.server 3456 &

# 2. 在 pi 对话中通过 browser 工具操作页面
#    浏览器自动通过 guard proxy 访问 http://localhost:3456

# 3. 开发完成后清理
pkill -f "python3 -m http.server"
pkill -f betterwright  # 关闭浏览器 daemon（可选，闲置 ~15 分钟自动关闭）
```

### 4.4 备选：Windows Edge + CDP

如需在 Windows 端 Edge 中可视化调试，可将 Edge 启动为 CDP 模式：

```powershell
# Windows PowerShell 中执行
Start-Process msedge -ArgumentList `
  "--remote-debugging-port=9222",`
  "--user-data-dir=$env:TEMP\edge-cdp-profile"
```

WSL 中通过 `http://localhost:9222` 连接（mirrored 网络模式下 `localhost` 即 Windows）。

---

## 五、开发流程与进度追踪

> 本节定义了从"开始开发"到"模块交付"的完整工作流，包含 todo 插件使用、`docs/todo.md` 更新及 git 操作。

### 4.1 启动前 — git pull

- **每次开始任何开发工作前，必须先执行 `git pull`**，确保本地代码与进度文件（`docs/todo.md`）为最新。
- 若 pull 发现 `docs/todo.md` 有冲突，优先以远程为准（人工合并后再继续）。

### 4.2 微小事务追踪 — todo 插件（必须使用）

- 每个模块的开发拆分为**微小事务**（如"实现 BState dataclass"、"写 stub.py 规则映射"、"联调 S2 验证"），**必须使用 todo 工具追踪**。
- todo 工具创建规范：
  - `subject`：简短动作描述（如"实现 small_model/stub.py"）
  - `description`：指向 spec 对应章节与验收标准
  - `status`：`in_progress` 时设 `activeForm`（如"编写 stub 规则映射"）
  - 任务完成**立即**标记 `completed`，不攒到模块末批量关闭。
- todo 工具中的任务应与 `docs/开发规划.md` 的阶段/模块对应，形成"阶段→模块→微小事务"三级粒度。

### 4.3 `docs/todo.md` — 模块级进度追踪

- 文件路径：`docs/todo.md`（仓库根 docs 下，活动文件）。
- 格式：Markdown 表格，对齐 `docs/开发规划.md` 的阶段与模块划分。
- 最少包含字段：**阶段** | **模块** | **状态**（未开始/进行中/已完成）| **负责人** | **最近更新**。
- 示例：
  ```
  ## 试飞控制系统 — 模块进度
  
  | 阶段 | 模块 | 状态 | 负责人 | 最近更新 |
  |---|---|---|---|---|
  | 阶段A | venv-A/B 创建 | ✅ 已完成 | — | 2026-07-23 |
  | 阶段A | msgpack S0 互通验证 | ✅ 已完成 | — | 2026-07-23 |
  | 阶段F | small_model/stub.py | 🚧 进行中 | — | 2026-07-23 |
  | 阶段F | rosbridge/publisher.py | ⬜ 未开始 | — | — |
  ```

### 4.4 模块完成时的自动更新规则

- **每个模块（如 `阶段F small_model stub`）完成时**：
  1. 将 `docs/todo.md` 中该模块行状态改为 `✅ 已完成`、更新"最近更新"时间戳。
  2. 将 todo 插件中该模块所有子任务全部标记 `completed`。
  3. **立即执行 `git push`**，将进度变更推送到远端（确保进度不丢失、跨会话可见）。
- 若一个阶段的所有模块均已完成，在 `docs/todo.md` 顶部标记阶段为 `✅ 已完成`。

### 4.5 模块完成时 — git push

- 每完成一个模块（含代码 + `docs/todo.md` 更新 + todo 插件状态同步），**必须 `git push`**。
- 不等到阶段全部完成才 push——push 粒度 = 模块完成粒度。
- push 前检查：确认 `docs/todo.md` 和所有代码文件已被 `git add`。