#!/bin/bash
# 后端 B 启动脚本 — 先 source ROS 再 activate venv-B
set -e
source /opt/ros/noetic/setup.bash
source .venv-B/bin/activate
exec python -m backend_B.main
