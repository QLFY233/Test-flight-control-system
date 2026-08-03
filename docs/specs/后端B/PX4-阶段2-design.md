# PX4 阶段2 设计 — PX4 SITL + MAVROS 接入

> 状态：**设计定稿（2026-08-02）**，编码前按 §12 回填核实。
> 权威依据：总体架构 §3.4（下游可替换）、后端B-design §5（ROS 桥/阶段抽象）、接口冻结（schema_version=2 不变）。
> 版本锁定：**Ubuntu 20.04 + ROS Noetic → PX4-Autopilot v1.13.3 + Gazebo Classic 11 + MAVROS 1.20.1**（2026-08-02 核实修正，`gz_x500`/Ignition 在 focal 不可用）。

---

## 1. 目标与范围

**目标**：将下游无人机实现从 sim-drone（运动学假无人机）替换为 **PX4 飞控固件软件在环仿真（SITL）+ Gazebo Classic 世界 + MAVROS 桥**，验证"大模型 → α 动作编码 → 端侧小模型目标点 → 真实飞控执行"完整链路，为外场真机（阶段四）铺路。

**范围**：
- ✅ 本设计：PX4 SITL 环境、MAVROS 桥、`Phase2Adapter`（offboard 状态机 + NED/ENU 变换）、B 侧改动面、安全设计、S8 验收
- ❌ 不含：ego-planner 在线避障 + 雷达点云（阶段4，仅留 `Planner` 接口挂点）；蒸馏小模型 α / 端侧小模型训练（独立远期任务）；真机移植（阶段四）

**不变量（与阶段1 完全一致）**：
- BState / `field.yaml` / A 侧 / 前端 **全部保持 ENU**（z 向上）——NED↔ENU 变换单点收敛在 rosbridge 层
- `small_model` 上层（动作编码 → 目标点 → 夹紧）**零改动**
- A↔B 接口冻结 `schema_version=2` **零改动**（B 上行 payload 字段不变，仅数值语义为 ENU）

---

## 2. 版本锁定与环境准备（2026-08-02 已核实）

| 组件 | 版本 | 安装方式 | 状态 |
|---|---|---|---|
| PX4-Autopilot | **v1.13.3**（tag） | `git clone --recursive -b v1.13.3 https://github.com/PX4/PX4-Autopilot.git $HOME/PX4-Autopilot`（仓库外，1GB+ 不入 git） | ⬜ 待装 |
| Gazebo | Classic 11.15.1 | apt（`ros-noetic-desktop-full` 含） | ✅ 本机已装 |
| gazebo-ros-pkgs | 2.9.3 | apt | ✅ 本机已装 |
| MAVROS | 1.20.1 | `apt install ros-noetic-mavros`（含 extras/msgs） | ✅ 已装（2026-08-02） |
| EGM96 重力数据 | — | `sudo /opt/ros/noetic/lib/mavros/install_geographiclib_datasets.sh`（**必跑**，否则 MAVROS 启动卡死） | ⬜ 待跑 |
| pymavlink | pip | `pip install pymavlink`（apt 不提供 python3-mavlink） | ⬜ 待装 |

> **PX4 v1.13.3 理由**：v1.14+ 弃用 ROS1 集成（mavros 官方支持线）；`gz_x500` 是 Ignition/Gz-Sim 模型，二进制不发 Ubuntu 20.04(focal) —— 唯一可行组合为 **Gazebo Classic 11 + `gazebo_iris`（v1.13.3 target 名）**。
> **WSLg 已可用**（`/mnt/wslg` 存在），GUI 与 `HEADLESS=1` 无头模式均可。

### 2.1 已装包核实记录（2026-08-02 本机实测）

```
$ dpkg -l | grep -E "ros-noetic-mavros"
ros-noetic-mavros        1.20.1-1focal
ros-noetic-mavros-msgs   1.20.1-1focal
$ cat /opt/ros/noetic/share/mavros/launch/px4.launch | grep fcu_url
<arg name="fcu_url" default="/dev/ttyACM0:57600" />
# SITL 时覆盖: fcu_url:=udp://:14540@127.0.0.1:14557
```

---

## 3. 启动编排（`start_px4_sitl.sh`，新增脚本）

```
[0] 清理旧进程 + rm /tmp/flight_control_AB.sock
[1] roscore
[2] PX4 SITL:   cd $HOME/PX4-Autopilot && HEADLESS=1 make px4_sitl gazebo_iris
                 (首次编译 15~30min, 产物 cache 于 build/ 目录; iris 模型首次下载)
[3] MAVROS:     roslaunch mavros px4.launch fcu_url:=udp://:14540@127.0.0.1:14557
                 (gcs_url 留空; 等 /mavros/state 的 connected=true)
[4] Backend-B:  PHASE=2 $PROJ/backend-B/run_b.py   (或 lifecycle 路径)
[5] Backend-A:  run_a.py (与 start_all.sh 相同)
```

- PX4 SITL 监听 UDP 14540（mavros 收），mavros 回连 14557——仅本机回环，mirrored 网络模式无碍
- 端口：roscore 11311、mavlink 14540/14557、QGC 可另连 14550（不冲突）

---

## 4. 消息契约与坐标系

### 4.1 话题契约（阶段2）

| 话题 | 类型 | 方向 | 与阶段1 差异 |
|---|---|---|---|
| `/mavros/setpoint_raw/local` | `mavros_msgs/PositionTarget` | B→PX4 | **类型变化**（PoseStamped → PositionTarget），adapter 适配 |
| `/mavros/local_position/pose` | `geometry_msgs/PoseStamped` | PX4→B | 类型不变，subscriber 复用（quat [x,y,z,w]→[w,x,y,z] 重排逻辑已有） |
| `/mavros/local_position/velocity_local` | `geometry_msgs/TwistStamped` | PX4→B | 类型不变 |
| `/mavros/imu/data` | `sensor_msgs/Imu` | PX4→B | 类型不变 |
| `/mavros/state` | `mavros_msgs/State` | PX4→B | **新增**（offboard 状态机输入：connected/armed/mode） |
| `/mavros/cmd/arming` | `mavros_msgs/CommandBool` srv | B→PX4 | **新增**（ARM/DISARM） |
| `/mavros/set_mode` | `mavros_msgs/SetMode` srv | B→PX4 | **新增**（OFFBOARD / AUTO.LAND 切换） |

> mavros 的 `local_position` 话题由 `px4flow`/`local_position` 插件发布，无需额外配置；`velocity_local` 为 NED 速度（mavros 已按 `frame_id` 语义发布，见 4.3 变换）。

### 4.2 PositionTarget 构造（权威定义：/opt/ros/noetic/share/mavros_msgs/msg/PositionTarget.msg）

```python
from mavros_msgs.msg import PositionTarget

msg = PositionTarget()
msg.coordinate_frame = PositionTarget.FRAME_LOCAL_NED   # = 1
# 位置控制（控 xyz + yaw）: 忽略速度/加速度/力/yaw_rate, 使用 yaw 字段
msg.type_mask = (PositionTarget.IGNORE_VX | PositionTarget.IGNORE_VY | PositionTarget.IGNORE_VZ
                 | PositionTarget.IGNORE_AFX | PositionTarget.IGNORE_AFY | PositionTarget.IGNORE_AFZ
                 | PositionTarget.IGNORE_YAW_RATE)      # = 8+16+32+64+128+256+2048 = 2552 (0x9F8)
msg.position = Point(x=..., y=..., z=...)               # NED 坐标!
msg.yaw = ...                                           # NED yaw (rad)
```

> **type_mask 必须整组设置**（不能只控 x 不控 y/z），否则 PX4 EKF 拒收（开发规划风险 2.5）。

### 4.3 NED ↔ ENU 坐标变换（核心难点，单点收敛）

**约定**：BState/field.yaml/A 侧/前端 = ENU（x 东、y 北、z 上）；PX4/mavros = NED（x 北、y 东、z 下）。

```python
def enu_to_ned(x, y, z): return (y, x, -z)   # 仅保留作数学定义/单测
# ⚠️ 实测修正 (2026-08-03, S8.3b 根因): 下行 setpoint 不再调用 enu_to_ned!
# mavros 1.20.1 的 setpoint_raw/local 插件 (local_cb) 对非 body 帧执行
# ENU→NED 变换 (含 yaw) — B 侧再变换 = 双重变换, FCU 收到 ENU 值当 NED:
#   takeoff z=+1.0(ENU) → FCU +1.0(向下!) → PX4 want_takeoff 永不成立
#   → 起飞状态机卡死 (爬升受限根因, ulog raw_sp.z=+1.0 实证)。
```

- 上行（PX4→B）：MAVROS 发布的话题本身已是 ROS ENU/FLU（REP-103，插件内 NED→ENU）——`subscriber` 恒等接入（曾误注入 ned_to_enu 造成双重变换）
- 下行（B→PX4）：`/mavros/setpoint_raw/local` 的 mavros 插件**负责 ENU→NED**——B 原样透传 ENU 位置与 yaw（`Phase2Adapter.publish_position` 不再变换）
- 速度/IMU 上行同构：mavros 已 ENU/FLU，恒等
- 验证锚点：PX4 SITL 起飞点 Gazebo 原点 = NED(0,0,0) = ENU(0,0,0)；field.yaml `home.position=[0,0,0.5]` 在 PX4 下即 NED(0,0,-0.5) 上方

---

## 5. Phase2Adapter 设计（`rosbridge/adapter.py` 新增）

### 5.1 接口（重构为 ABC，阶段切换只改 PHASE 环境变量）

```python
class SetpointAdapter:                    # ABC (新增)
    def publish_position(self, pos, yaw): ...   # ENU 入参
    def publish_velocity(self, vel): ...        # ENU 入参
    def preflight(self) -> bool: ...            # 起飞前准备 (阶段2: offboard 状态机)
    def emergency_land(self): ...               # 安全兜底 (阶段2: AUTO.LAND; 阶段1: 悬停点)

class Phase1Adapter(SetpointAdapter):     # 现有, 补 preflight/emergency_land 默认实现
class Phase2Adapter(SetpointAdapter):     # 新增, 见下
```

### 5.2 Offboard 状态机（Phase2Adapter 内部线程，20Hz）

```
        ┌──────────┐  首帧位置 setpoint   ┌────────────┐
        │ DISARMED │ ───────────────────▶ │ STREAMING  │  20Hz 发当前位置 setpoint
        └──────────┘                      └────────────┘  (ENU→NED), 持续 ≥3s
             ▲                                   │  (前置: 位置离 home < 2m 才允许继续)
             │ state.armed=false                 ▼
        ┌──────────┐   /mavros/cmd/arming     ┌────────────┐
        │  LANDED  │ ◀─────────────────────── │   ARMING   │  等 state.armed==true
        └──────────┘                          └────────────┘
             ▲                                       │
             │  emergency_land()                     │
             └────────────────────────────── ┌────────────┐
                                             │ OFFBOARD   │  ACTIVE: 20Hz 位置 setpoint
                                             └────────────┘  监测 state.mode

> ⚠️ **实测修正（2026-08-03）**：状态机实际顺序为 **STREAMING → 切 OFFBOARD → ARM → ACTIVE**，
> 即 **OFFBOARD 切换先于 ARM**（与官方 offboard 例程一致）。原因：OFFBOARD 模式下
> `flag_control_manual_enabled=false`，preArm 的 manual control 检查被跳过——否则无 RC
> 环境下 ARM 被拒 "Arming denied! manual control lost"。图中 LANDED→ARMING 路径仍用于
> 应急复位（disarm 后重 arm）。```

- **状态输入**：`/mavros/state`（`connected`/`armed`/`mode`，mavros 10Hz 默认），订阅回调写锁内状态
- **STREAMING 前置**：ARM 前必须已连续 stream ≥1s（工程 20Hz/3s，开发规划风险 1）；且当前位置距 `home` < 2m（防远距离意外 ARM）
- **顺序（实测修正）**：STREAMING ≥3s → **set_mode OFFBOARD**（验证 `state.mode==OFFBOARD`，若当前为 AUTO.* 模式且直切失败先 POSCTL 再重试）→ **ARM**（验证 `state.armed==true`）→ ACTIVE。**OFFBOARD 先于 ARM**（避开 preArm 的 manual control 检查；OFFBOARD 切换本身不要求已 ARM，官方 offboard 例程同序）
- **setpoint 流贯穿**：STREAMING→OFFBOARD→ARM 全程由独立流线程 20Hz 维持 setpoint（PX4 offboard 停发 ≥1s 自动退出），ACTIVE 后由 GoalPublisher 接管（无目标时持续发当前位置=悬停）
- **首帧防跳变**：STREAMING 首帧即发当前位置（复用 publisher 既有逻辑）
- **实测补强（2026-08-03）**：① preflight 等首帧真实位姿再 STREAMING（防合成默认位姿导致非预期小跳）；② 已武装且落地静止（2s 速度 <0.15m/s）→ 先 disarm 再 arm，强制 disarm→arm 边沿触发 PX4 takeoff 状态机（否则 landed 钳制锁死位置控制）；③ OFFBOARD→ARM 重试环（EKF/GPS home 未就绪时 PX4 拒切，实测撞窗口）
- **虚拟 RC（SITL 必需）**：无真遥控时 preArm 的 manual control 检查会拒 ARM（"manual control lost"）。方案：`COM_RC_IN_MODE=3`（first_valid）+ B 侧 `Phase2Adapter` 持续发中性 RC override（2Hz，ch1-3 中性 1500 / ch4 油门最低 1000 / **ch5-6 开关通道必须 1500**（0 会被解析为开关位置触发 RTL）/ 其余 0）。**三坑实测**：① `OverrideRCIn.channels` 必须 18 元素（8 元素序列化报错被静默吞）；② 通道值必须微抖（±1 PWM）——rc_update "limit processing if there's no update"，固定值永不发布 setpoint；③ `COM_RC_IN_MODE=1`（仅 MAVLINK 源）不匹配 rc_update 输出（恒 SOURCE_RC）→ RC 从未有效 → OFFBOARD 状态被 RC-lost failsafe 反复覆盖——**必须用 3**（first_valid）

### 5.3 动作语义映射（small_model 上层零感知）

| 动作 | 阶段1（sim-drone） | 阶段2（PX4） |
|---|---|---|
| `takeoff` | setpoint (x,y,1.0) 爬升 | offboard 位置 setpoint (x,y,home_z+1.0) 爬升（无需 AUTO.TAKEOFF） |
| `goto/move/climb/descend/yaw` | setpoint 目标点 | 同左，经 mavros setpoint_raw（插件内 ENU→NED）下发 |
| `hover` | 停发 setpoint → 仿真器自动悬停 | **持续 20Hz 发当前位置**（PX4 offboard 停发 ≥1s 自动退出！语义差异已修正）——2026-08-03 再修正：**捕获一次当前位置后锁定发布**（持续重锚=零恢复力→自由漂移实测） |
| `land` | setpoint z=0 | **set_mode AUTO.LAND**（不用 offboard 下压，避免触地检测干扰）——✅ 已实现（2026-08-03 S8.4）：component.set_land_handler → adapter.emergency_land，run_b.py/lifecycle.py 均接线；实飞落地 + disarm + status 流转 |
| `abort` | 清目标 + 悬停 | **`set_mode AUTO.LAND` 兜底**（比悬停更保守，安全设计）——✅ 已接线：dispatch set_abort_handler → adapter.emergency_land，且 `_check_offboard_lost` 在 `_emergency` 标志下不再重切 OFFBOARD（否则 1s 内 AUTO.LAND 被覆盖，实测） |
| `return_home` | setpoint home | offboard 位置 setpoint home |

### 5.4 故障与降级

| 故障 | 检测 | 处置 |
|---|---|---|
| offboard 丢失（mode 被切走/停发超时） | `state.mode != OFFBOARD` 且非主动切换 | 重新 STREAMING → 重切 OFFBOARD；连续失败 2 次 → `emergency_land()` + alert `offboard_lost` |
| MAVROS 失连 | `state.connected == false` 持续 >1s | 复用 monitor `drone_data_stale` 告警链路 + link alert |
| PX4 拒 ARM（不满足前置） | state 无变化 | alert + 停在 STREAMING 重试 |
| setpoint 发布异常 | publisher 异常计数 | 上报 + 停止推进状态机 |

---

## 6. B 侧代码改动面

| 文件 | 改动 | 回归影响 |
|---|---|---|
| `rosbridge/topics.py` | 加 `PHASE2_PREFIX="/mavros"` + 阶段2 话题/服务表（`setpoint_raw/local`、`state`、`cmd/arming`、`set_mode`） | 无（增量） |
| `rosbridge/adapter.py` | 抽 `SetpointAdapter` ABC；`Phase1Adapter` 补默认 `preflight/emergency_land`；新增 `Phase2Adapter`（状态机线程 + 变换 + PositionTarget） | 行为不变 |
| `rosbridge/subscriber.py` | phase 注入上行 NED→ENU 变换器（Phase1 恒等） | 无（默认 phase1） |
| `rosbridge/publisher.py` | 接口不变；`preflight()` 挂到组件启动序列 | 无 |
| `backend-B/lifecycle.py` / `run_b.py` | adapter 工厂按 `PHASE` 环境变量（默认 1）创建；phase2 时先 `preflight` 再启目标点线程 | 无（默认 phase1 全链路复跑） |
| `monitor/` | 新增 `OffboardLostDetector`（可选先导，依赖 state 输入） | 无（新注册器） |
| 新增 `start_px4_sitl.sh` | 一键 SITL 编排（§3） | 无 |
| `config/` | 无 schema 变化；可选 `phase` 字段（默认 1） | 无 |

> **接口冻结影响**：无。B 上行 `event:pose/telemetry/status/alert` payload 字段与单位不变（ENU 语义），`schema_version=2` 保持。

---

## 7. 安全设计

1. **坐标系单点变换**：ENU↔NED 仅存在于 `Phase2Adapter` 与 subscriber 注入点，杜绝散落错配（z 反向 = 撞地，最高危）
2. **ARM 前置三重检查**：stream ≥3s + 距 home <2m + `state.connected`
3. **abort/land 保守化**：一律 `AUTO.LAND`，不依赖 offboard 下压
4. **offboard 丢失自动降级**：重试 → LAND，并走既有 alert 链路（monitor 节流 2s）
5. **boundary 夹紧保留在 ENU 侧**（small_model 既有逻辑），PX4 无场地概念——夹紧后目标点仍超界则 reject（既有回路）
6. **人工介入通道**：RC 遥控器/切换开关在 PX4 侧优先于 offboard（PX4 原生行为，文档声明，不额外实现）
7. **首帧防跳变** + 20Hz 平滑下发（既有 publisher 逻辑保留）

---

## 8. S8 验收清单（编码完成后执行）

> **实测状态（2026-08-03 16:00）**：S8.1~S8.8 **全项实飞验收完成**。S8.2 已按 §4.3 修正重验（空中同刻 rostopic z=+0.870 ↔ B 上行 z=+0.870，同号同值）；S8.4 land→AUTO.LAND 实飞（落地 + disarm + status 流转）；S8.5 A 侧 REST abort 闭环；S8.6 强制切 POSCTL → 自动重切恢复（失败路径单测覆盖）；S8.7 B 134/134 + A 56/56；S8.8 ARM 前置 alert 单测覆盖（27/27）。遗留（非验收项）：monitor overaccel/out_of_boundary 误报（PX4 IMU 含重力），待后续适配。

| # | 验收项 | 判定 |
|---|---|---|
| S8.1 | 环境就绪：PX4 v1.13.3 SITL + Gazebo iris 启动，`rostopic echo /mavros/state` `connected=true` | ✅ 实测通过（2026-08-03） |
| S8.2 | NED/ENU 正确性：起飞后 `rostopic echo /mavros/local_position/pose` → B 侧/前端显示 **z 为 ENU 正值**；`curl /api/current-pose` 与 rostopic 对照（z 反号校验） | ✅ 重验通过（2026-08-03）：空中同刻 rostopic z=+0.870 ↔ B 上行 z=+0.870（同号同值）；REST current-pose 地面 -0.232 ↔ rostopic -0.23 一致。此前“通过”系双端同源空转（subscriber 曾再变换），§4.3 修正后重验无变换 |
| S8.3 | 全链路：β/α 翻译 `takeoff` → 端侧小模型目标点 → offboard 起飞爬升；`goto` 移动到位；`hover` 稳定保持 | ✅ 核心已验（2026-08-03）：mini-A 注入 takeoff(1.0) → 爬升至 1.0m（4 次复现），1m 悬停 6s 漂移 ≤0.04m；ulog groundtruth z 0.73→-0.60 实证物理离地（金标准） |
| S8.3b | **已解决（根因：mavros setpoint_raw 双重 ENU→NED 变换）**：mavros 1.20.1 local_cb 对非 body 帧自动 ENU→NED，B 侧 adapter 再变换 → FCU 收到 ENU 值当 NED，takeoff z=+1.0(向下) → want_takeoff 永不成立 → 起飞状态机卡死。修复：adapter 透传 ENU（§4.3），另加固 GoalPublisher 限速推进（ramp 以 setpoint 为锚非当前位置）与 hover 锁定保持点 | ✅ 已解决（2026-08-03 实飞） |
| S8.4 | `land` → AUTO.LAND 落地（z≈0，螺旋桨停转）；B 侧 `event:status` 状态流转正确 | ✅ 实测通过（2026-08-03）：takeoff→land 动作序列，`land → AUTO.LAND (handler injected)` → 落地 z≈-0.26 + disarm（螺旋桨停）；status executing→completed |
| S8.5 | abort：A 侧 `POST /api/sessions/{id}/abort` → 无人机切 AUTO.LAND 安全落地 | ✅ 链路已验（2026-08-03）：mini-A call.abort → AUTO.LAND 2s 落地 + **A 侧 REST `POST /api/sessions/{id}/abort` 回测闭环**（→ aborted → B emergency_land） |
| S8.6 | offboard 丢失模拟（强制切 POSCTL）→ alert `offboard_lost` + 自动恢复或 LAND | ✅ 实测通过（2026-08-03）：悬停中 rosservice 强制切 POSCTL → B 检测 `offboard lost` → 自动重切 `re-engaged`（恢复）；连续失败 2 次 → emergency_land + alert(critical) 由单测 T2 覆盖 |
| S8.7 | 阶段1 回归：`PHASE=1` 假无人机 S0~S7 复跑全绿 | ✅ 通过（2026-08-03）：B 134/134 + A 56/56；PHASE 默认 1、subscriber 恒等、small_model 上层零感知（代码路径检查） |
| S8.8 | 安全：ARM 前置（未 stream / 距 home 超 2m）被拒，alert 提示 | ✅ 单测覆盖（2026-08-03）：preflight 拒绝路径 → alert(preflight_refused, warning)（test_s8_safety T4，27/27）；ARM 前置三重检查已在 preflight 实现 |

---

## 9. 风险与冲突检查

| # | 风险 | 对策 |
|---|---|---|
| 0 | Ubuntu 20.04 用 `gz_x500`/Ignition → 二进制不存在、PX4 v1.14+ 弃 ROS1 | **锁定 v1.13.3 + Gazebo Classic 11**，`make px4_sitl gazebo_iris` |
| 0.5 | MAVROS 启动卡死报 EGM96 | 装包后必跑 `install_geographiclib_datasets.sh`（§2） |
| 1 | offboard 切换前无 setpoint stream → 拒切 | STREAMING ≥3s（20Hz）流线程贯穿全程；**OFFBOARD 先于 ARM**（实测修正，见 §5.2） |
| 2.5 | type_mask 只控单轴 → EKF 拒收 | 整组设置（§4.2 常量位或，=2552） |
| **8（实测新增→已解决）** | **无人机爬升受限 ~0.4m**（setpoint=EKF+0.075 恒定、thrust 悬停化） | ✅ **根因 2026-08-03 定位**：mavros 1.20.1 setpoint_raw local_cb 对非 body 帧自动 ENU→NED，B 侧 adapter 再变换 = 双重变换 → FCU 收到 ENU 值当 NED（takeoff z=+1.0 向下）→ want_takeoff 永不成立 → 起飞状态机卡死。修复：adapter 透传 ENU + GoalPublisher ramp/hover 加固 + preflight 起飞边沿（S8.3b，实飞验证） |
| **9（实测新增）** | COM_RC_IN_MODE=1 不匹配 rc_update 输出（SOURCE_RC）→ RC 从未有效 → offboard 被 RC-lost failsafe 覆盖 | **必须 COM_RC_IN_MODE=3**（first_valid）+ 虚拟 RC（§5.2 三坑） |
| 2 | python3-mavlink apt 不提供 | pip `pymavlink` |
| **3（新）** | **NED/ENU 变换错配（z 反向撞地）** | 单点收敛 + S8.2 双端对照验证 |
| **4（新）** | PX4 源码 clone/编译慢（v1.13.3 递归子模块 1GB+） | 仓库外 `$HOME/PX4-Autopilot`，首次编译 15~30min 一次性成本 |
| **5（新）** | Gazebo iris 模型首次启动下载资源 | 首启联网等待；后续本地缓存 |
| **6（新）** | WSL2 UDP 端口冲突（14540/14557） | mirrored 模式本机回环无碍；QGC 14550 不冲突 |
| **7（新）** | offboard 悬停语义误解（停发=退出） | §5.3 语义表修正：hover=持续发当前位置 |

---

## 10. 核实回填表（对齐后端B-design §12 模式，2026-08-02）

| 核实项 | 方式 | 结论 | 关联节 |
|---|---|---|---|
| mavros apt 包名/版本 | 本机 `apt install ros-noetic-mavros/msgs` | ✅ 1.20.1 安装成功（2026-08-02） | §2 |
| PositionTarget 字段/type_mask 常量 | 本机 `/opt/ros/noetic/share/mavros_msgs/msg/PositionTarget.msg` | ✅ FRAME_LOCAL_NED=1；IGNORE_* 位定义；位置控制 mask=2552 | §4.2 |
| State 模式名 | 本机 `State.msg` | ✅ `OFFBOARD` / `AUTO.LAND` / `POSCTL` | §4.1/§5.3 |
| arming/set_mode 服务 | 本机 `mavros_msgs/srv/` | ✅ `CommandBool.srv`（/mavros/cmd/arming）、`SetMode.srv`（/mavros/set_mode） | §4.1 |
| px4.launch fcu_url | 本机 `/opt/ros/noetic/share/mavros/launch/px4.launch` | ✅ 默认 `/dev/ttyACM0:57600`；SITL 覆盖 `udp://:14540@127.0.0.1:14557` | §3 |
| PX4 SITL 跑法 | 2026-08-02 版本锁定 + 2026-08-03 实测 | ✅ `make px4_sitl gazebo_iris`（v1.13.3 的 target 名，**非** gazebo-classic_iris——那是 v1.14+ 命名）；HEADLESS=1 无头 + `tail -f /dev/null \|` 保活 stdin（否则 pxh 读到 EOF 退出）；依赖：kconfiglib/menuconfig（pip）、future、libgstreamer1.0-dev、build/mavlink 头生成、sitl_gazebo configure 缓存（改源后需清 stamp） | §2/§3 |
| EGM96 | 官方安装脚本 | ✅ 已装（2026-08-02） | §2 |
| pymavlink | pip | ✅ 已装 venv-B（2026-08-02） | §2 |
| PX4 v1.13.3 源码 | clone 实测 | ✅ 已 clone `$HOME/PX4-Autopilot`（--recursive -b v1.13.3，19 子模块）+ 编译成功（2026-08-03） | §2 |
| offboard 状态机顺序 | 实测 | ✅ **OFFBOARD 先于 ARM**（官方例程序，避开 manual control 检查） | §5.2 |
| 虚拟 RC 必需性 | 实测 | ✅ SITL 无 RC → preArm 拒（"manual control lost"）；COM_RC_IN_MODE=3 + 18 通道中性微抖 override（三坑详见 §5.2） | §5.2 |
| 爬升受限 | 实测（遗留→已解决） | ✅ 根因：mavros setpoint_raw 双重 ENU→NED（§4.3 修正 + S8.3b，实飞验证：takeoff 爬升 1.0m×4、悬停漂移 ≤0.04m、abort→AUTO.LAND 2s 落地） | §8/§9 |
