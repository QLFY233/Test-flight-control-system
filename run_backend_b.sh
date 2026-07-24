#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f /opt/ros/noetic/setup.bash ]; then
    source /opt/ros/noetic/setup.bash
fi
if [ -f ros_ws/devel/setup.bash ]; then
    source ros_ws/devel/setup.bash
fi

if [ -d .venv-B ]; then
    source .venv-B/bin/activate
fi

export ROS_MASTER_URI="${ROS_MASTER_URI:-http://localhost:11311}"
export ROS_IP="${ROS_IP:-127.0.0.1}"

exec python -m backend_B.main "$@"
