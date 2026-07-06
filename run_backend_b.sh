#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Backend B launcher
#
# Sources the ROS1 Noetic environment, the catkin workspace (if present),
# and the Backend B Python 3.8 virtual environment, then starts Backend B.
#
# Usage:
#   ./run_backend_b.sh
#   ./run_backend_b.sh --stub
#   ./run_backend_b.sh --socket /tmp/flight_control_AB.sock
#   ./run_backend_b.sh --field config/field.yaml --constraints config/default_constraints.yaml
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Source ROS1 Noetic
if [ -f /opt/ros/noetic/setup.bash ]; then
    source /opt/ros/noetic/setup.bash
else
    echo "WARNING: /opt/ros/noetic/setup.bash not found. ROS may not be available."
fi

# Source catkin workspace (if exists)
if [ -f ros_ws/devel/setup.bash ]; then
    source ros_ws/devel/setup.bash
fi

# Activate Backend B virtual environment
if [ -d .venv-B ]; then
    source .venv-B/bin/activate
else
    echo "WARNING: .venv-B virtual environment not found."
    echo "Create it with: python3.8 -m venv .venv-B && source .venv-B/bin/activate && pip install -r venv-B-requirements.txt"
fi

# Set ROS environment variables
export ROS_MASTER_URI="${ROS_MASTER_URI:-http://localhost:11311}"
export ROS_IP="${ROS_IP:-127.0.0.1}"

# Run Backend B
exec python -m backend_B.main "$@"
