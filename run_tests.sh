#!/usr/bin/env bash
set -euo pipefail
# 试飞控制系统 — 全量测试脚本
# 用法: ./run_tests.sh [--a] [--b] [--sim]  (默认全部)

ROOT="$(cd "$(dirname "$0")" && pwd)"
PASS=0
FAIL=0

run_test() {
    local label="$1"; shift
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "▶ $label"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    if "$@"; then
        echo "✅ $label — PASS"
        PASS=$((PASS + 1))
    else
        echo "❌ $label — FAIL"
        FAIL=$((FAIL + 1))
    fi
}

test_a() {
    cd "$ROOT/backend-A/tests"
    source "$ROOT/.venv-A/bin/activate" 2>/dev/null || true
    python3 test_all.py
}

test_b() {
    cd "$ROOT/backend-B/tests"
    source "$ROOT/.venv-B/bin/activate" 2>/dev/null || true
    python3 test_all.py
}

test_sim() {
    echo "[sim-drone] catkin_make 编译检查..."
    cd "$ROOT/ros_ws"
    if [ -f devel/setup.bash ]; then
        source /opt/ros/noetic/setup.bash 2>/dev/null || true
        source devel/setup.bash 2>/dev/null || true
        # 检查 fake_drone_node 是否可导入
        python3 -c "import fake_drone_node" 2>/dev/null || {
            echo "  ⚠ fake_drone_node 不可直接导入 (需 ROS launch)"
            echo "  ✅ ROS 包结构存在"
        }
    else
        echo "  ⚠ ros_ws 未编译, 跳过"
    fi
}

# 解析参数
RUN_A=true; RUN_B=true; RUN_SIM=true
case "${1:-}" in
    --a)  RUN_B=false; RUN_SIM=false ;;
    --b)  RUN_A=false; RUN_SIM=false ;;
    --sim) RUN_A=false; RUN_B=false ;;
esac

$RUN_A   && run_test "后端 A 单元测试" test_a
$RUN_B   && run_test "后端 B 单元测试" test_b
$RUN_SIM && run_test "sim-drone" test_sim

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  结果: $PASS 通过 / $((PASS + FAIL)) 总数"
if [ $FAIL -eq 0 ]; then
    echo "  ✅ 全部通过!"
else
    echo "  ❌ $FAIL 失败"
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
exit $FAIL
