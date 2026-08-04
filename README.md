# 试飞控制系统

> 大模型理解试飞意图 → α 翻译为动作编码 → 端侧小模型产出目标点 → 模拟无人机执行
> 龙虾模式:中枢大模型 β 调度多组件,人类只与 β 对话。

## 仓库结构

```
flight-control-system/
├── backend-A/           # Agent 中枢 (Python 3.10+)
├── backend-B/           # ROS 飞控桥 (Python 3.8 + ROS Noetic)
├── frontend/            # 静态前端 (原生 HTML/JS + Three.js/ECharts)
├── sim-drone/           # 阶段1 假无人机 (catkin 包)
├── ros_ws/              # catkin workspace
├── config/              # field.yaml + default_constraints.yaml
├── shared/              # A/B 共用协议常量 (软链)
├── docs/                # 设计文档 + 模块进度
└── start_all.sh         # 一键启动
```

## 环境与依赖安装

系统: **Ubuntu 20.04 LTS (WSL2, mirrored 网络模式)** + **ROS Noetic** + **Python 3.8 (B侧) / 3.10 (A侧)**

### 0. apt 基础包 (ROS Noetic 已装则跳过)

```bash
sudo apt update
sudo apt install -y \
  ros-noetic-desktop-full \
  python3-catkin-tools python3-rosdep \
  python3.10 python3.10-venv python3.10-dev  # deadsnakes PPA (A侧 Python)
```

> deadsnakes PPA:`sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt update`

### 1. B 侧运行依赖 (Python 3.8 + rospy, 经 venv-B 继承系统 site-packages)

```bash
# venv-B 必须用 --system-site-packages 才能继承 rospy/msgpack 等系统包
cd /home/nibuhao/Test-flight-control-system
/usr/bin/python3 -m venv --system-site-packages .venv-B
source .venv-B/bin/activate
pip install -r venv-B-requirements.txt   # 主要是 pyyaml (其余从系统继承)
```

B 侧依赖 (apt 已装,继承):
- `rospy 1.17.4`, `geometry_msgs`, `sensor_msgs`, `mavros_msgs`, `mavros` (装 PX4 时)
- `msgpack 0.6.2` (apt python3-msgpack), `numpy 1.17.4`, `scipy 1.3.3`, `PyYAML`

### 2. A 侧运行依赖 (Python 3.10)

```bash
python3.10 -m venv .venv-A
source .venv-A/bin/activate
pip install -r venv-A-requirements.txt
# FastAPI 0.136.3 / Pydantic AI 2.0.0 / SQLAlchemy 2.0.51 / Uvicorn / msgpack / openai
```

LLM 配置 (`.env`, 不入库):

```bash
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-...
# 讯飞 STT/TTS (语音模块,可选)
XF_APP_ID=...
XF_API_KEY=...
XF_API_SECRET=...
XF_API_PASSWORD=...
```

### 3. 假无人机 (阶段1, 已编译)

```bash
cd ros_ws && catkin_make -DPYTHON_EXECUTABLE=/usr/bin/python3
source devel/setup.bash
rosrun sim_drone fake_drone_node.py
# 或 roscore + roslaunch sim_drone fake_drone.launch
```

### 4. PX4 SITL + Gazebo (阶段2, 远期 — 不阻塞先导)

> 阶段2 才需要。**关键版本锁定**: PX4 v1.13.3 + Gazebo Classic 11 + MAVROS 1.20.1。
> 不要在 Ubuntu 20.04 上追 `gz_x500` / Gazebo Harmonic — 那需要 Ubuntu 22.04+。

#### 4.1 MAVROS + GeographicLib 重力数据 (MAVROS 启动必需)

```bash
sudo apt install -y \
  ros-noetic-mavros ros-noetic-mavros-msgs ros-noetic-mavros-extras \
  ros-noetic-geographic-msgs geographiclib-tools libgeographic-dev

# MAVROS 启动必须的重力模型数据 (缺它启动卡死报 EGM96)
wget https://raw.githubusercontent.com/mavlink/mavros/ros/mavros/scripts/install_geographiclib_datasets.sh
sudo bash install_geographiclib_datasets.sh
```

#### 4.2 PX4-Autopilot v1.13.3 源码与编译

```bash
cd ~
git clone -b release/1.13 --recursive https://github.com/PX4/PX4-Autopilot.git
cd PX4-Autopilot

# 装编译工具链 (一次性,约 10 分钟)
bash Tools/setup/ubuntu.sh

# 编译 SITL + Gazebo Classic 11 仿真器 (iris 四旋翼模型)
make px4_sitl gazebo-classic_iris      # ← 不是 gz_x500
# 无头模式 (WSL2 推荐):
HEADLESS=1 make px4_sitl gazebo-classic_iris
```

#### 4.3 启动 PX4 SITL + MAVROS

```bash
# 终端1: PX4 SITL + Gazebo Classic
cd ~/PX4-Autopilot
make px4_sitl gazebo-classic_iris

# 终端2: MAVROS (连 SITL 的 UDP 14540)
source /opt/ros/noetic/setup.bash
roslaunch mavros px4.launch fcu_url:="udp://:14540@127.0.0.1:14557"
```

#### 4.4 PX4 offboard 关键约束 (写代码时必须遵守)

- **预热**: 切 offboard 前必须 stream setpoint **≥2Hz 至少 1 秒**,工程上 **20Hz 跑 3s** 最稳;先 ARM 再 `set_mode OFFBOARD`
- **setpoint 消息**: `mavros_msgs/PositionTarget` (不是 PoseStamped),发到 `/mavros/setpoint_raw/local`
- **type_mask 位掩码**: 位 0-2=位置,3-5=速度,6-8=加速度,9=force,10=yaw,11=yaw_rate;置 1 = 忽略;**整组设置** (不能只给 x 不给 y/z)
- **无 GPS 室内**: `param set EKF2_GPS_CTRL 0` + `COM_RCL_EXCEPT 4`,位置源喂 `mavros/vision_pose/pose`
- **WSL2 Gazebo**: Classic 11 的 **GUI(gzclient)不可用**——OGRE 1.9 需直接 OpenGL 上下文,WSL2 全间接(WSLg/VcXsrv 均失败,黑屏/崩溃/segfault)。**物理仿真(gzserver 无头)正常**;3D 可视化用**前端 Three.js Scene3D**(浏览器 WebGL,实时渲染仿真位姿),见 [前端详细设计 §7](docs/specs/前端/前端详细设计-组件接口定义.md)。Gz-Sim/Harmonic 也不可用 (需 GL 4.2+)

详见 `docs/specs/后端B/PX4-阶段2-design.md`（阶段2 完整设计，含 S8 验收与 Gazebo GUI 限制 §11）。

## 一键启动

```bash
bash start_all.sh
# roscore → sim-drone → Backend B → Backend A → 验证 REST + LLM
# 访问 http://localhost:8000
```

停止:

```bash
pkill -f 'run_a.py\|run_b.py\|fake_drone\|roscore'
```

## 测试

```bash
# B 侧 (venv-B)
cd backend-B && python tests/test_all.py        # 58 项

# A 侧 (venv-A)
cd backend-A && python tests/test_all.py        # 47 项
```

## 文档

- 设计文档: `docs/specs/` (总体架构 / 后端A / 后端B / 前端 / 接口冻结 / 开放式接口 / 测试路线图)
- 模块进度: `docs/todo.md`
- 开发规划: `docs/开发规划.md` (阶段 A~M)

先导阶段 A~L 全部完成 (S0~S7 验收通过),阶段 M (PX4 SITL) 远期。