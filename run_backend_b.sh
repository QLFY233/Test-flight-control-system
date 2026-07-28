#!/usr/bin/env bash
set -euo pipefail

# 0) 验证 Python 版本 (B 侧需 Python 3.8)
PY_VER=$(python3 -c 'import sys; print(sys.version_info[:2])' 2>/dev/null || echo "unknown")
if [[ "$PY_VER" != "(3, 8)" ]]; then
  echo "WARNING: 预期 Python 3.8 (ROS Noetic), 当前: $PY_VER" >&2
  echo "继续执行, 但 venv-B 可能不兼容" >&2
fi

# 1) ROS 环境(Noetic)
source /opt/ros/noetic/setup.bash
# 2) 若有 catkin workspace(source devel)
if [ -f ros_ws/devel/setup.bash ]; then source ros_ws/devel/setup.bash; fi
# 3) 激活 B 侧 venv
source .venv-B/bin/activate
# 4) 环境变量
export ROS_MASTER_URI=http://localhost:11311
export ROS_IP=127.0.0.1
# 5) 启动
exec python -m backend_B.main "$@"
