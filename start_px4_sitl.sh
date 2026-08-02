#!/bin/bash
#===========================================================
# PX4 阶段2 一键启动 — PX4 SITL + MAVROS + 本系统 (PX4-阶段2-design.md §3)
# 用法: bash start_px4_sitl.sh
# 前置: PX4-Autopilot v1.13.3 已 clone 于 $PX4_DIR (默认 ~/PX4-Autopilot)
#===========================================================
set -e
PROJ=$(cd "$(dirname "$0")" && pwd)
PX4_DIR=${PX4_DIR:-$HOME/PX4-Autopilot}
export ROS_MASTER_URI=http://localhost:11311
export ROS_IP=127.0.0.1
export no_proxy=localhost,127.0.0.1,$no_proxy

# 清理旧进程 (含 roscore 重启清 ROS 死节点)
echo "[0/5] 清理旧进程..."
pkill -9 -f "px4\|gzserver\|mavros\|run_a.py\|run_b.py\|roscore\|rosmaster" 2>/dev/null || true
sleep 2
rm -f /tmp/flight_control_AB.sock

source /opt/ros/noetic/setup.bash

# [1/5] roscore
echo "[1/5] 启动 roscore..."
roscore &>/tmp/roscore.log &
sleep 4
rostopic list &>/dev/null || { echo "ERROR: roscore 启动失败"; exit 1; }
echo "  ✅ roscore OK"

# [2/5] PX4 SITL (Gazebo Classic, 无头)
echo "[2/5] 启动 PX4 SITL (gazebo-classic_iris)..."
if [ ! -d "$PX4_DIR" ]; then
    echo "ERROR: PX4 源码不存在: $PX4_DIR (先 clone: git clone --recursive -b v1.13.3 ...)"
    exit 1
fi
cd "$PX4_DIR"
HEADLESS=1 nohup make px4_sitl gazebo-classic_iris &>/tmp/px4-sitl.log &
PX4_PID=$!
sleep 5
# 等 SITL 就绪 (UDP 14540 端口监听)
for i in $(seq 1 60); do
    ss -uln 2>/dev/null | grep -q ":14540 " && break
    sleep 1
done
ss -uln 2>/dev/null | grep -q ":14540 " || { echo "  ⚠️ SITL 未在 60s 内就绪, 查看: tail -50 /tmp/px4-sitl.log"; }
echo "  ✅ PX4 SITL OK (PID=$PX4_PID, 首次编译 15~30min)"

# [3/5] MAVROS
echo "[3/5] 启动 MAVROS (fcu_url=udp://:14540@127.0.0.1:14557)..."
nohup roslaunch mavros px4.launch fcu_url:=udp://:14540@127.0.0.1:14557 &>/tmp/mavros.log &
MAVROS_PID=$!
for i in $(seq 1 20); do
    sleep 1
    if rostopic echo -n1 /mavros/state --noarr 2>/dev/null | grep -q "connected: True"; then
        echo "  ✅ MAVROS OK (connected, PID=$MAVROS_PID, ${i}s)"
        break
    fi
done
rostopic echo -n1 /mavros/state --noarr 2>/dev/null | grep -q "connected: True" || {
    echo "  ⚠️ MAVROS 未连接, 查看: tail -30 /tmp/mavros.log (EGM96 装了吗?)"
}

# [4/5] Backend B (PHASE=2)
echo "[4/5] 启动 Backend B (PHASE=2)..."
source "$PROJ/ros_ws/devel/setup.bash" 2>/dev/null || true
PHASE=2 nohup /usr/bin/python3 -u "$PROJ/backend-B/run_b.py" &>/tmp/backend-b.log &
B_PID=$!
sleep 8
grep -q "READY" /tmp/backend-b.log 2>/dev/null || { echo "  ⚠️ Backend B 未就绪: tail /tmp/backend-b.log"; }
echo "  ✅ Backend B OK (PID=$B_PID)"

# [5/5] Backend A
echo "[5/5] 启动 Backend A..."
fuser -k 8000/tcp 2>/dev/null || true
"$PROJ/.venv-A/bin/python3" -u "$PROJ/backend-A/run_a.py" &>/tmp/backend-a.log &
A_PID=$!
for i in $(seq 1 20); do
    sleep 1
    grep -q "Application startup complete" /tmp/backend-a.log 2>/dev/null && break
done
grep -q "Application startup complete" /tmp/backend-a.log 2>/dev/null || {
    echo "  ⚠️ Backend A 启动超时, 查看: tail /tmp/backend-a.log"
}
echo "  ✅ Backend A OK (PID=$A_PID)"

echo ""
echo "==============================================="
echo "  等待链路稳定 (15s, 含 offboard preflight)..."
echo "==============================================="
sleep 15
echo "--- 进程状态 ---"
echo "PX4 SITL:   $(pgrep -fc px4 2>/dev/null || echo 0) 进程"
echo "MAVROS:     $(pgrep -fc mavros 2>/dev/null || echo 0) 进程"
echo "Backend B:  $(pgrep -cf run_b.py 2>/dev/null || echo 0) 进程"
echo "Backend A:  $(pgrep -cf run_a.py 2>/dev/null || echo 0) 进程"
echo "--- offboard 状态 ---"
grep -E "preflight|offboard|ACTIVE|emergency" /tmp/backend-b.log 2>/dev/null | tail -5 || true
echo "--- REST ---"
echo -n "  health:      "; curl -sf http://127.0.0.1:8000/api/health 2>/dev/null || echo "FAIL"
echo -n "  current-pose: "; curl -sf http://127.0.0.1:8000/api/current-pose 2>/dev/null || echo "FAIL"
echo ""
echo "  启动完成! 前端: http://localhost:8000 | 日志: tail -f /tmp/{px4-sitl,mavros,backend-b,backend-a}.log"
echo "  停止: pkill -f 'px4\|gzserver\|mavros\|run_a.py\|run_b.py\|roscore'"
echo "==============================================="
