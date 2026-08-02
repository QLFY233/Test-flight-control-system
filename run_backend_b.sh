#!/usr/bin/env bash
set -euo pipefail

# B-3 修复: 原 `python -m backend_B.main` 模块名不存在 (目录名 backend-B 含连字符),
# 必然 ModuleNotFoundError。改为 cd 进 backend-B 直接跑 main.py (其内部会把自身目录
# 加入 sys.path 以导入 lifecycle/state 等模块), config-dir 指向项目根 config。
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)

# 0) 验证 Python 版本 (B 侧需 Python 3.8)
PY_VER=$(python3 -c 'import sys; print(sys.version_info[:2])' 2>/dev/null || echo "unknown")
if [[ "$PY_VER" != "(3, 8)" ]]; then
  echo "WARNING: 预期 Python 3.8 (ROS Noetic), 当前: $PY_VER" >&2
  echo "继续执行, 但 venv-B 可能不兼容" >&2
fi

# 1) ROS 环境(Noetic)
source /opt/ros/noetic/setup.bash
# 2) 若有 catkin workspace(source devel)
if [ -f "$SCRIPT_DIR/ros_ws/devel/setup.bash" ]; then source "$SCRIPT_DIR/ros_ws/devel/setup.bash"; fi
# 3) 激活 B 侧 venv
source "$SCRIPT_DIR/.venv-B/bin/activate"
# 4) 环境变量
export ROS_MASTER_URI=http://localhost:11311
export ROS_IP=127.0.0.1
# 5) 启动 (cd 进 backend-B, 使 main.py 的 sys.path 自举生效)
cd "$SCRIPT_DIR/backend-B"
exec python main.py --config-dir "$SCRIPT_DIR/config" "$@"
