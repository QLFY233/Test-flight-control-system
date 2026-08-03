#!/bin/bash
#===========================================================
# PX4 posix rcS 参数补丁 — 幂等注入 (PX4-阶段2-design.md §2/§5.2)
# 用法: bash patch_px4_rcs.sh [PX4_DIR]     (默认 $PX4_DIR 或 ~/PX4-Autopilot)
#
# 背景: PX4 在仓库外 ($HOME/PX4-Autopilot), 手工改 rcS 换机器/重装即丢。
# 本脚本把参数段做成 marker 包裹的幂等注入:
#   - 无补丁      → 在 AUTOCNF 块前插入 marker 段
#   - 旧手工补丁  → 剥除后替换为 marker 段 (2026-08-03 前手工注入的无 marker 版)
#   - marker 已存在 → 内容一致 no-op / 不一致则整体替换 (版本升级路径,
#                     marker 匹配用版本无关前缀, 任意旧版均可被替换)
# 同时补丁源码树与 build 目录副本 (运行时读的是 build 副本,
# cmake 不保证随源码内容变更重新拷贝, 故两处都直接打)。
#
# 变更记录:
#   v1 (2026-08-03): 初版 — 等价 2026-08-03 实测手工补丁
#   v2 (2026-08-03): 删 EKF2_EN (v1.13.3 无此参数, rcS 报 not found);
#                    SYS_MC_EST_GROUP=2 保留 (rcS 亦按 PX4_ESTIMATOR=ekf2 默认设置, 双保险)
#===========================================================
set -e
PX4_DIR=${1:-${PX4_DIR:-$HOME/PX4-Autopilot}}

# marker 匹配用版本无关前缀; BLOCK 内首行携带版本号
MARK_BEGIN_PREFIX="# >>> flight-control-system px4 patch"
MARK_END="# <<< flight-control-system px4 patch <<<"

# ── 补丁段内容 (v2) ──
BLOCK=$(cat <<'EOF'
# >>> flight-control-system px4 patch (v2) >>>
# 试飞控制系统阶段2 适配 (PX4-阶段2-design.md §2/§5.2), 由 patch_px4_rcs.sh 幂等注入
# COM_RC_IN_MODE=3 (first_valid): 接受 B 侧 Phase2Adapter 的 mavlink 虚拟 RC 中性
#   override; =1 (仅 MAVLINK 源) 不匹配 rc_update 输出 (恒 SOURCE_RC) → RC 从未有效
#   → offboard 被 RC-lost failsafe 反复覆盖 (2026-08-03 实测根因)
echo "[px4-patch] flight-control-system params applied (v2)"
param set COM_RC_IN_MODE 3
param set SYS_MC_EST_GROUP 2
# SITL 电池模拟阈值 (防低电压强制 disarm+RTL)
param set BAT1_V_EMPTY 2.7
param set BAT1_CAPACITY 5000
# RC/offboard lost 不触发 PX4 原生 failsafe (B 侧自身有 offboard 丢失检测 + emergency_land 兜底)
param set NAV_RCL_ACT 1
param set COM_OBL_ACT 0
param set COM_OBL_RC_ACT 0
# <<< flight-control-system px4 patch <<<
EOF
)

# ── 2026-08-03 前的手工补丁行 (无 marker), 用于剥除 ──
OLD_LINES=$(cat <<'EOF'
# ── 试飞控制系统阶段2 适配 (PX4-阶段2-design.md §2) ──
# COM_RC_IN_MODE=1: 接受 mavlink 虚拟 RC (B 侧 Phase2Adapter 发中性 override),
#   否则无 RC 环境 ARM 被拒 "manual control lost" (必须在 manual_control 模块启动前)
echo PX4_PARAM_TEST_OK_MARKER
param set COM_RC_IN_MODE 3
param set EKF2_EN 1
param set SYS_MC_EST_GROUP 2
# SITL 电池模拟阈值 (防低电压强制 disarm+RTL)
param set BAT1_V_EMPTY 2.7
param set BAT1_CAPACITY 5000
# RC/offboard lost 不触发 failsafe (B 侧自身有 offboard 丢失检测 + emergency_land 兜底)
param set NAV_RCL_ACT 1
param set COM_OBL_ACT 0
param set COM_OBL_RC_ACT 0
EOF
)

ANCHOR='if [ $AUTOCNF = yes ]'   # 插入锚点: reset_all 擦除之后、AUTOCNF 块之前

patch_one() {
    local f="$1"
    if [ ! -f "$f" ]; then
        echo "  ⏭️  跳过 (不存在): $f"
        return 0
    fi
    if grep -qF "$MARK_BEGIN_PREFIX" "$f"; then
        # marker 段已存在: 抽取现有段, 与期望一致则 no-op, 否则整体替换
        local cur
        cur=$(awk -v bp="$MARK_BEGIN_PREFIX" -v e="$MARK_END" '
            index($0,bp)==1 {inb=1} inb {print} $0==e {inb=0}' "$f")
        if [ "$cur" = "$BLOCK" ]; then
            echo "  ✅ 已是最新 (no-op): $f"
            return 0
        fi
        awk -v bp="$MARK_BEGIN_PREFIX" -v e="$MARK_END" -v nb="$BLOCK" '
            index($0,bp)==1 {inb=1; print nb; next}
            $0==e {inb=0; next}
            !inb {print}' "$f" > "$f.tmp" && mv "$f.tmp" "$f"
        echo "  ♻️  已替换旧版补丁段: $f"
        return 0
    fi
    # 剥除旧手工补丁 (整行精确匹配, 不误伤其他行)
    if grep -qF "试飞控制系统阶段2 适配" "$f"; then
        grep -vxFf <(printf '%s\n' "$OLD_LINES") "$f" > "$f.tmp" && mv "$f.tmp" "$f"
        echo "  🧹 已剥除旧手工补丁: $f"
    fi
    # 锚点前插入
    if ! grep -qF "$ANCHOR" "$f"; then
        echo "  ❌ 锚点未找到 ($ANCHOR), rcS 版本不符: $f" >&2
        return 1
    fi
    awk -v anchor="$ANCHOR" -v nb="$BLOCK" '
        !done && index($0, anchor)==1 {print ""; print nb; done=1}
        {print}' "$f" > "$f.tmp" && mv "$f.tmp" "$f"
    echo "  💉 已注入补丁段: $f"
}

echo "[px4-patch] PX4_DIR=$PX4_DIR"
[ -d "$PX4_DIR" ] || { echo "❌ PX4 源码不存在: $PX4_DIR" >&2; exit 1; }
patch_one "$PX4_DIR/ROMFS/px4fmu_common/init.d-posix/rcS"
patch_one "$PX4_DIR/build/px4_sitl_default/etc/init.d-posix/rcS"
echo "[px4-patch] done (重启 SITL 后生效)"
