#!/bin/bash
#===========================================================
# PX4 阶段2 一键启动 — PX4 SITL + MAVROS + 本系统 (PX4-阶段2-design.md §3)
# 用法: bash start_px4_sitl.sh
# 前置: PX4-Autopilot v1.13.3 已 clone 于 $PX4_DIR (默认 ~/PX4-Autopilot)
#===========================================================
set -e
PROJ=$(cd "$(dirname "$0")" && pwd)
export PROJ   # 供 mavros_px4.launch 的 $(env PROJ) 展开 (config_yaml 指向项目内配置)
PX4_DIR=${PX4_DIR:-$HOME/PX4-Autopilot}
export ROS_MASTER_URI=http://localhost:11311
export ROS_IP=127.0.0.1
export no_proxy=localhost,127.0.0.1,$no_proxy

# 清理旧进程 (含 roscore 重启清 ROS 死节点; tail -f /dev/null 是 SITL stdin 保活管道)
# pkill 用 ERE: 必须为 | 而非 \| (\| 只匹配字面竖线, 历史上清理从未生效!);
# [] 字符类技巧防匹配脚本自身 (start_px4_sitl.sh 含 px4 字样)
echo "[0/5] 清理旧进程..."
pkill -9 -f "[b]in/px4|[m]ake px4_sitl|[s]itl_run|[g]zserver|[m]avros|[r]un_a.py|[r]un_b.py|[r]oscore|[r]osmaster|[t]ail -f /dev/null" 2>/dev/null || true
sleep 2
rm -f /tmp/flight_control_AB.sock

echo "  ✅ 清理完成 (残留: px4=$(pgrep -fc '[b]in/px4' 2>/dev/null || echo 0) roscore=$(pgrep -fc '[r]osmaster' 2>/dev/null || echo 0))"

# set -e 下 source 失败会静默退出 — 显式报错便于定位
source /opt/ros/noetic/setup.bash || { echo "ERROR: source /opt/ros/noetic/setup.bash 失败 (ROS Noetic 未装?)"; exit 1; }

# [1/5] roscore
echo "[1/5] 启动 roscore..."
roscore &>/tmp/roscore.log &
sleep 4
rostopic list &>/dev/null || { echo "ERROR: roscore 启动失败"; exit 1; }
echo "  ✅ roscore OK"

# [2/5] PX4 SITL (Gazebo Classic, 无头)
echo "[2/5] 启动 PX4 SITL (gazebo_iris)..."
if [ ! -d "$PX4_DIR" ]; then
    echo "ERROR: PX4 源码不存在: $PX4_DIR (先 clone: git clone --recursive -b v1.13.3 ...)"
    exit 1
fi
# rcS 参数补丁 (幂等注入, COM_RC_IN_MODE=3/BAT1_*/NAV_RCL_ACT/COM_OBL_ACT — 实测修正 §5.2)
bash "$PROJ/patch_px4_rcs.sh" "$PX4_DIR"
cd "$PX4_DIR" || { echo "ERROR: 无法进入 $PX4_DIR"; exit 1; }
# v1.13.3 target 名为 gazebo_iris (gazebo-classic_* 是 v1.14+ 命名);
# tail -f /dev/null | 保活 stdin — 否则本脚本退出后 pxh 读到 EOF, PX4 随即退出 (实测)
tail -f /dev/null | HEADLESS=1 nohup make px4_sitl gazebo_iris &>/tmp/px4-sitl.log &
PX4_PID=$!
sleep 5
# 等 SITL 就绪 — PX4 onboard mavlink 实例绑定 UDP 14580 (发往 mavros 14540;
# 14540 是 MAVROS 侧端口, 此处等不到)。双保险: 日志出现启动成功标记也算。
for i in $(seq 1 90); do
    ss -uln 2>/dev/null | grep -q ":14580 " && break
    grep -q "Startup script returned successfully" /tmp/px4-sitl.log 2>/dev/null && sleep 3 && break
    sleep 1
done
ss -uln 2>/dev/null | grep -q ":14580 " && echo "  ✅ PX4 SITL OK (PID=$PX4_PID)" || { echo "  ⚠️ SITL 未在 90s 内就绪, 查看: tail -50 /tmp/px4-sitl.log"; }

# [3/5] MAVROS
# _conn/timesync_rate:=0.0 + _time/timesync_mode:=NONE — 禁用 sys_time 插件的
# TIMESYNC 收发 (2026-08-03 实测): mavros 主动 10Hz 发 TIMESYNC → PX4 必回 →
# WSL2 时钟校正致 offset 突变 → "TM : Time jump detected" 每 ~45s 一次。
# NONE 模式下消息时间戳回落 ROS 本地时间 (B 侧本就走 wall time, 无影响)。
echo "[3/5] 启动 MAVROS (fcu_url=udp://:14540@127.0.0.1:14557, timesync disabled)..."
nohup roslaunch "$PROJ/mavros_px4.launch" fcu_url:=udp://:14540@127.0.0.1:14557 &>/tmp/mavros.log &
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
# 等 EKF 预热 (local_position 开始发布 + GPS home 就绪) — 否则 B preflight
# 切 OFFBOARD 会被 PX4 拒 (2026-08-03 实测: B 启动过快撞 EKF 预热窗口)
echo "  等待 EKF 预热 (local_position + home set)..."
for i in $(seq 1 30); do
    timeout 2 rostopic echo -n1 /mavros/local_position/pose --noarr &>/dev/null && break
    sleep 1
done
grep -q "home set" /tmp/px4-sitl.log 2>/dev/null || sleep 5
# 2026-08-03 实测补强: local_position 首条消息 ≠ EKF 已收敛 — SITL 刚启动 ~15s 即
# preflight 时 EKF 估计漂移 → 无人机追踪漂移估计飞出 ~13m (gz 模型位置实证)。
# 固定加 30s 收敛窗口 (S8 手动验证时 SITL 均运行 >2min, 从未漂移)。
echo "  EKF 收敛窗口 30s..."
sleep 30
echo "  ✅ EKF OK"

	# PX4 SITL 重启后 COM_RC_IN_MODE 可能被旧持久化参数覆盖为 1，
	# 导致 RC-lost failsafe 反复激活 → offboard 被拒。启动 B 前确保参数正确。
	echo "  检查 PX4 RC/offboard 参数..."
	rosrun mavros mavparam set COM_RC_IN_MODE 3 2>/dev/null || true
	rosrun mavros mavparam set NAV_RCL_ACT 1 2>/dev/null || true
	rosrun mavros mavparam set COM_OBL_ACT 0 2>/dev/null || true
	echo "  ✅ RC/offboard 参数已确认"

# [4/5] Backend B (PHASE=2)
echo "[4/5] 启动 Backend B (PHASE=2)..."
cd "$PROJ"   # run_b.py 虽自 chdir, 统一起始目录防日志/相对路径意外
source "$PROJ/ros_ws/devel/setup.bash" 2>/dev/null || true
PHASE=2 nohup /usr/bin/python3 -u "$PROJ/backend-B/run_b.py" &>/tmp/backend-b.log &
B_PID=$!
sleep 8
grep -q "READY" /tmp/backend-b.log 2>/dev/null || { echo "  ⚠️ Backend B 未就绪: tail /tmp/backend-b.log"; }
echo "  ✅ Backend B OK (PID=$B_PID)"

# [5/5] Backend A
# .env 有 DEEPSEEK_API_KEY 等 (gitignore 不入库); run_a.py 无 dotenv 加载,
# 必须在此 source 进环境 (否则 α/β degraded, 2026-08-03 实测)
if [ -f "$PROJ/.env" ]; then
    set -a; source "$PROJ/.env"; set +a
fi
echo "[5/5] 启动 Backend A..."
cd "$PROJ"   # run_a.py create_app('config') 用相对路径, 必须在项目根启动
A_PORT=${BACKEND_A_PORT:-8000}
fuser -k ${A_PORT}/tcp 2>/dev/null || true
# fuser 杀死旧进程后端口释放有延迟 (TIME_WAIT), 等真正空闲再启动防 bind 竞态
for i in $(seq 1 10); do
    ss -tln 2>/dev/null | grep -q ":${A_PORT} " || break
    sleep 0.5
done
# WSL mirrored 模式下 Windows 侧服务 (XDAgent 等) 会间歇抢占 8000 — WSL 内杀不掉,
# 启动失败 (bind 竞态) 则自动降级重试 8001 (前端 base_url 同源自适应, 不受影响)
start_a() {
    BACKEND_A_PORT=$1 "$PROJ/.venv-A/bin/python3" -u "$PROJ/backend-A/run_a.py" &>/tmp/backend-a.log &
    for i in $(seq 1 20); do
        sleep 1
        # uvicorn 先打 "startup complete" 再报 bind 错误 — 必须同时排除 bind 失败
        if grep -q "address already in use" /tmp/backend-a.log 2>/dev/null; then
            return 1
        fi
        if grep -q "Application startup complete" /tmp/backend-a.log 2>/dev/null; then
            sleep 1
            if ! grep -q "address already in use" /tmp/backend-a.log 2>/dev/null; then
                return 0
            fi
            return 1
        fi
    done
    return 1
}
if ! start_a "$A_PORT"; then
    if [ "$A_PORT" != "8001" ]; then
        echo "  ⚠️ 端口 ${A_PORT} bind 失败 (Windows 侧服务抢占?), 降级重试 8001"
        A_PORT=8001
        start_a "$A_PORT" || echo "  ⚠️ A 启动失败 (8001 也失败), 查看: tail /tmp/backend-a.log"
    else
        echo "  ⚠️ A 启动失败, 查看: tail /tmp/backend-a.log"
    fi
fi
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
echo -n "  health:      "; curl -sf http://127.0.0.1:${A_PORT:-8000}/api/health 2>/dev/null || echo "FAIL"
echo -n "  current-pose: "; curl -sf http://127.0.0.1:${A_PORT:-8000}/api/current-pose 2>/dev/null || echo "FAIL"
echo ""
echo "  启动完成! 前端: http://localhost:${A_PORT:-8000} | 日志: tail -f /tmp/{px4-sitl,mavros,backend-b,backend-a}.log"
echo "  停止: pkill -f '[b]in/px4|[g]zserver|[m]avros|[r]un_a.py|[r]un_b.py|[r]oscore|[t]ail -f /dev/null'"
echo "==============================================="
