#!/bin/bash
#===========================================================
# 试飞控制系统 — 一键启动脚本
# 用法: bash start_all.sh
#===========================================================
set -e
# B-8: 自推导项目根, 不再硬编码家目录 (原 /home/nibuhao/... 指向他机, 本机直接失败)
PROJ=$(cd "$(dirname "$0")" && pwd)
cd "$PROJ"
rm -f /tmp/flight_control_AB.sock

export ROS_MASTER_URI=http://localhost:11311
export ROS_IP=127.0.0.1

# 绕过本地代理 (防止 SSE 流被拦截)
export no_proxy=localhost,127.0.0.1,$no_proxy

# 从 .env 加载配置
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# 清理旧进程 (包括 roscore 重启来清除 ROS 死节点)
# ⚠️ pkill -f 用 ERE: 交替须写 | 而非 \| (原 \| 只匹配字面竖线, 清理从未生效 → 残留节点名冲突)
echo "[0/4] 清理旧进程..."
pkill -9 -f "roscore|rosmaster|fake_drone|run_a.py|run_b.py" 2>/dev/null || true
sleep 2

#===========================================================
# 1. roscore
#===========================================================
echo "[1/4] 启动 roscore..."
source /opt/ros/noetic/setup.bash
roscore &>/tmp/roscore.log &
sleep 4
source /opt/ros/noetic/setup.bash
rostopic list &>/dev/null || { echo "ERROR: roscore 启动失败"; exit 1; }
echo "  ✅ roscore OK"

#===========================================================
# 2. sim-drone (假无人机)
#===========================================================
echo "[2/4] 启动 sim-drone..."
source /opt/ros/noetic/setup.bash
source "$PROJ/ros_ws/devel/setup.bash"
/usr/bin/python3 -u "$PROJ/ros_ws/src/sim-drone/scripts/fake_drone_node.py" &>/tmp/sim-drone.log &
sleep 3
rostopic list 2>/dev/null | grep -q drone || { echo "ERROR: sim-drone 启动失败"; cat /tmp/sim-drone.log; exit 1; }
echo "  ✅ sim-drone OK ($(rostopic list 2>/dev/null | grep drone | wc -l) topics)"

#===========================================================
# 3. Backend B (飞控桥, Python 3.8 + ROS)
#===========================================================
echo "[3/4] 启动 Backend B..."
source /opt/ros/noetic/setup.bash
source "$PROJ/ros_ws/devel/setup.bash"
/usr/bin/python3 -u "$PROJ/backend-B/run_b.py" &>/tmp/backend-b.log &
B_PID=$!
sleep 5
grep -q "READY" /tmp/backend-b.log 2>/dev/null || { echo "ERROR: Backend B 启动失败"; cat /tmp/backend-b.log; exit 1; }
echo "  ✅ Backend B OK (PID=$B_PID)"

#===========================================================
# 4. Backend A (Agent 中枢, Python 3.10)
#===========================================================
echo "[4/4] 启动 Backend A..."
fuser -k 8000/tcp 2>/dev/null || true  # 释放端口
# B-8: 改用项目 venv-A (Py3.10+), 不再硬编码 pyenv 3.10.19 路径
"$PROJ/.venv-A/bin/python3" -u "$PROJ/backend-A/run_a.py" &>/tmp/backend-a.log &
A_PID=$!
for i in $(seq 1 20); do
    sleep 1
    if grep -q "Application startup complete" /tmp/backend-a.log 2>/dev/null; then
        echo "  ✅ Backend A OK (PID=$A_PID, ${i}s)"
        break
    fi
done
grep -q "Application startup complete" /tmp/backend-a.log 2>/dev/null || {
    echo "  ⚠️ Backend A 启动超时, 查看: tail /tmp/backend-a.log"
}

#===========================================================
# 验证
#===========================================================
echo ""
echo "==============================================="
echo "  等待链路稳定 (10s)..."
echo "==============================================="
sleep 10

echo ""
echo "--- 进程状态 ---"
echo "roscore:    $(pgrep -c roscore 2>/dev/null || echo 0) 进程"
echo "sim-drone:  $(rostopic list 2>/dev/null | grep -c drone || echo 0) topics active"
echo "Backend B:  $(pgrep -cf run_b.py 2>/dev/null || echo 0) 进程"
echo "Backend A:  $(pgrep -cf run_a.py 2>/dev/null || echo 0) 进程"

echo ""
echo "--- REST API ---"
echo -n "  health:      "; curl -sf http://127.0.0.1:8000/api/health 2>/dev/null || echo "FAIL"
echo -n "  link-status: "; curl -sf http://127.0.0.1:8000/api/link-status 2>/dev/null || echo "FAIL"
echo -n "  current-pose: "; curl -sf http://127.0.0.1:8000/api/current-pose 2>/dev/null || echo "FAIL"

echo ""
echo "--- LLM β Chat 测试 ---"
echo "  (等待 DeepSeek 响应, 约 5~15s...)"
RESP=$(curl -sf --max-time 30 -X POST http://127.0.0.1:8000/api/chat/beta \
  -H "Content-Type: application/json" \
  -d '{"message":"你好，请用一句话介绍你自己"}' 2>/dev/null) || true
if [ -n "$RESP" ]; then
    echo "$RESP" | grep -o '"content":"[^"]*"' | head -1 | sed 's/"content":"/  /;s/"//'
else
    echo "  ⚠️ LLM 无响应 (检查 API key 是否正确)"
fi

echo ""
echo "==============================================="
echo "  启动完成! 访问 http://localhost:8000"
echo "  查看日志: tail -f /tmp/backend-{a,b}.log"
echo "  停止: pkill -f 'run_a.py\|run_b.py\|fake_drone\|roscore'"
echo "==============================================="
