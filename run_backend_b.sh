#!/usr/bin/env bash
set -euo pipefail

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
