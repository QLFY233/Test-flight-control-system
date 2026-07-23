#!/usr/bin/env python3
"""
Generate 7 transparent-background PNG images for the 试飞控制系统技术报告.
Font: Noto Sans CJK JP (supports Chinese characters).
Style: Professional, clean, no emoji, transparent background.
"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Arc
import matplotlib.font_manager as fm
import numpy as np
import os

# ── Global style ──────────────────────────────────────────────
plt.rcParams['font.family'] = 'Noto Sans CJK JP'
plt.rcParams['axes.unicode_minus'] = False

OUTDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'report_images')
os.makedirs(OUTDIR, exist_ok=True)

# Color palette – professional muted tones
C_PRIMARY   = '#1a5276'   # dark navy
C_SECONDARY = '#2980b9'   # medium blue
C_ACCENT    = '#e67e22'   # warm amber
C_LIGHT     = '#d4e6f1'   # pale blue
C_DARK      = '#2c3e50'   # dark slate
C_GREY      = '#7f8c8d'   # grey
C_GREEN     = '#27ae60'   # green
C_RED       = '#c0392b'   # red
C_WHITE     = '#ffffff'
C_BG_LIGHT  = '#f8f9fa'

def save_transparent(fig, name, dpi=150):
    path = os.path.join(OUTDIR, name)
    fig.savefig(path, dpi=dpi, transparent=True, bbox_inches='tight',
                pad_inches=0.3, facecolor='none', edgecolor='none')
    plt.close(fig)
    print(f'  Saved: {path}')


def draw_rounded_box(ax, x, y, w, h, color=C_PRIMARY, text='', text_color=C_WHITE,
                     fontsize=9, alpha=1.0, linewidth=1.5):
    """Draw a rounded rectangle with centered text."""
    rect = FancyBboxPatch((x, y), w, h,
                          boxstyle='round,pad=0.15', facecolor=color,
                          edgecolor=C_DARK, linewidth=linewidth, alpha=alpha)
    ax.add_patch(rect)
    if text:
        ax.text(x + w/2, y + h/2, text, ha='center', va='center',
                fontsize=fontsize, color=text_color, weight='bold')


def draw_arrow(ax, x1, y1, x2, y2, color=C_DARK, lw=1.2, style='simple'):
    """Draw an arrow from (x1,y1) to (x2,y2)."""
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle='->', color=color, lw=lw,
                               connectionstyle='arc3,rad=0' if style == 'simple' else 'arc3,rad=0.1'))


# ═══════════════════════════════════════════════════════════════
# Image 1: 报告整体结构示意图
# ═══════════════════════════════════════════════════════════════
def image1_structure():
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.set_xlim(0, 10); ax.set_ylim(0, 6)
    ax.axis('off')
    ax.set_facecolor('none')

    chapters = [
        ('一', '项目背景\n与立项依据'),
        ('二', '项目目标\n与总体方案'),
        ('三', '系统总体\n架构'),
        ('四', '实现流程'),
        ('五', '各重要模块\n介绍'),
        ('六', '关键技术\n介绍'),
        ('七', '项目价值'),
        ('八', '规划进展\n与实施计划'),
    ]

    # Layout: 2 rows × 4 columns
    box_w, box_h = 1.8, 1.6
    gap_x, gap_y = 0.5, 0.8
    start_x, start_y = 0.8, 2.5

    for i, (num, title) in enumerate(chapters):
        col = i % 4
        row = 1 - (i // 4)
        x = start_x + col * (box_w + gap_x)
        y = start_y + row * (box_h + gap_y)

        if row == 0:
            color = C_PRIMARY
        else:
            color = C_SECONDARY

        draw_rounded_box(ax, x, y, box_w, box_h, color=color,
                        text=f'{num}\n{title}', fontsize=9)

        # Arrow to next
        if i < 3 or (4 <= i < 7):
            ax.annotate('', xy=(x + box_w + gap_x*0.3, y + box_h/2),
                       xytext=(x + box_w + gap_x*0.7, y + box_h/2),
                       arrowprops=dict(arrowstyle='->', color=C_DARK, lw=1.5))

    # Down arrow from #4 to #5
    ax.annotate('', xy=(start_x + box_w/2, start_y - gap_y*0.3),
               xytext=(start_x + box_w/2, start_y + gap_y*0.3),
               arrowprops=dict(arrowstyle='->', color=C_DARK, lw=1.5))

    # Title
    ax.text(5, 5.3, '试飞控制系统技术报告 — 整体结构', ha='center', fontsize=16,
            weight='bold', color=C_DARK)

    save_transparent(fig, '01_报告整体结构.png', dpi=150)


# ═══════════════════════════════════════════════════════════════
# Image 2: 未来驾驶舱人-AI协同概念图
# ═══════════════════════════════════════════════════════════════
def image2_human_ai():
    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.set_xlim(0, 10); ax.set_ylim(0, 5.5)
    ax.axis('off')

    # Title
    ax.text(5, 5.1, '未来驾驶舱人-AI协同概念', ha='center', fontsize=15,
            weight='bold', color=C_DARK)

    # Left: Human Pilot
    draw_rounded_box(ax, 0.8, 2.0, 2.5, 2.2, color='#2471a3',
                    text='飞行员\n（决策权威）\n\n· 态势感知\n· 关键判断\n· 最终决策', fontsize=9)

    # Right: AI Assistant
    draw_rounded_box(ax, 6.7, 2.0, 2.5, 2.2, color='#1e8449',
                    text='智能助手\n（辅助执行）\n\n· 信息整合\n· 方案建议\n· 任务执行', fontsize=9)

    # Center: Interaction box
    draw_rounded_box(ax, 3.8, 2.3, 2.4, 1.6, color=C_ACCENT,
                    text='协同交互\n\n审核确认\n交叉检查\n透明解释', fontsize=9)

    # Arrows
    ax.annotate('', xy=(3.8, 3.1), xytext=(3.3, 3.1),
               arrowprops=dict(arrowstyle='<->', color=C_DARK, lw=2))
    ax.annotate('', xy=(6.7, 3.1), xytext=(6.2, 3.1),
               arrowprops=dict(arrowstyle='<->', color=C_DARK, lw=2))

    # Labels
    ax.text(3.55, 3.7, '飞行方案', fontsize=8, ha='center', color=C_DARK)
    ax.text(6.45, 3.7, '调度指令', fontsize=8, ha='center', color=C_DARK)
    ax.text(3.55, 2.5, '审核确认', fontsize=8, ha='center', color=C_DARK)
    ax.text(6.45, 2.5, '执行反馈', fontsize=8, ha='center', color=C_DARK)

    # 5 principles box
    ax.text(5, 0.7, '5条人-AI协同原则（Saunders et al., 2026）', ha='center',
            fontsize=10, weight='bold', color=C_DARK)
    principles = [
        '1. 音频优先用于关键信息',
        '2. 系统权威根据情境调整',
        '3. 多模态合理组合而非简单叠加',
        '4. 关键动作须飞行员交叉确认',
        '5. 支持返回驾驶舱时态势恢复',
    ]
    for i, p in enumerate(principles):
        ax.text(5, 0.3 - i*0.25, p, ha='center', fontsize=7.5, color=C_GREY)

    save_transparent(fig, '02_人AI协同概念图.png', dpi=150)


# ═══════════════════════════════════════════════════════════════
# Image 3: 四阶段研究路径推进图
# ═══════════════════════════════════════════════════════════════
def image3_roadmap():
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.set_xlim(0, 12); ax.set_ylim(0, 4)
    ax.axis('off')

    ax.text(6, 3.6, '四阶段研究路径推进图', ha='center', fontsize=15, weight='bold', color=C_DARK)

    phases = [
        ('阶段一', '需求与\n架构设计', '已完成', C_GREEN),
        ('阶段二', '核心组件\n开发', '待启动', C_SECONDARY),
        ('阶段三', '集成联调\n地面仿真', '后续', C_ACCENT),
        ('阶段四', '外场演示\n与评估', '远期', C_PRIMARY),
    ]

    outputs = [
        '架构规格\n接口规范\n测试路线图',
        '前端界面\n智能中枢\n执行桥\n边缘执行模型',
        '全链路打通\n接口验证\n场景测试',
        '真实飞行演示\n性能评估\n总结报告',
    ]

    for i, ((pname, ptitle, status, color), output) in enumerate(zip(phases, outputs)):
        x = 1.2 + i * 2.8
        # Phase box
        draw_rounded_box(ax, x, 1.4, 2.3, 1.2, color=color,
                        text=f'{pname}\n{ptitle}\n（{status}）', fontsize=8.5)
        # Output box
        draw_rounded_box(ax, x, 0.1, 2.3, 1.1, color=C_LIGHT, text_color=C_DARK,
                        text=f'产出:\n{output}', fontsize=7.5, alpha=0.7)

        # Arrow between phases
        if i < 3:
            ax.annotate('', xy=(x + 2.3 + 0.15, 2.0),
                       xytext=(x + 2.3 + 0.35, 2.0),
                       arrowprops=dict(arrowstyle='->', color=C_DARK, lw=2))

    # Time axis
    ax.plot([1.2, 10.6], [2.9, 2.9], 'k-', lw=1.5)
    ax.text(11, 2.9, '时间', fontsize=9, va='center', color=C_DARK)
    for i in range(5):
        x = 1.2 + i*2.35
        ax.plot([x, x], [2.85, 2.95], 'k-', lw=1)

    save_transparent(fig, '03_四阶段路径图.png', dpi=150)


# ═══════════════════════════════════════════════════════════════
# Image 4: 系统总体架构图 — 龙虾模式
# ═══════════════════════════════════════════════════════════════
def image4_architecture():
    fig, ax = plt.subplots(figsize=(14, 9))
    ax.set_xlim(0, 14); ax.set_ylim(0, 9)
    ax.axis('off')

    ax.text(7, 8.5, '系统总体架构 — 龙虾模式', ha='center', fontsize=16,
            weight='bold', color=C_DARK)

    # Central hub: 中枢大模型
    center_x, center_y = 7, 5
    hub = FancyBboxPatch((center_x-1.8, center_y-0.6), 3.6, 1.2,
                         boxstyle='round,pad=0.2', facecolor=C_RED,
                         edgecolor=C_DARK, linewidth=2.5)
    ax.add_patch(hub)
    ax.text(center_x, center_y, '中枢大模型\n（龙虾中枢·规划调度）', ha='center',
            va='center', fontsize=10, color='white', weight='bold')

    # Message bus ring
    bus_circle = plt.Circle((center_x, center_y), 3.2, fill=False,
                            edgecolor=C_DARK, linewidth=1.5, linestyle='--')
    ax.add_patch(bus_circle)
    ax.text(center_x + 2.8, center_y + 2.5, '统一消息总线', fontsize=8,
            color=C_GREY, ha='center')

    # Satellite components (arranged in a circle)
    satellites = [
        ('离散数据\n翻译模型', 0),
        ('边缘执行\n模型', 45),
        ('路径规划器\n+雷达感知', 90),
        ('数据监控\n程序', 145),
        ('数据分析\n工具集', 200),
        ('看板驱动器', 240),
        ('历史数据\n查询', 290),
        ('前端\n交互界面', 330),
    ]

    for name, angle_deg in satellites:
        angle = np.radians(angle_deg)
        sx = center_x + 4.5 * np.cos(angle) - 0.7
        sy = center_y + 3.5 * np.sin(angle) - 0.4

        color = C_SECONDARY if angle_deg != 330 else C_ACCENT
        draw_rounded_box(ax, sx, sy, 1.4, 0.8, color=color, text=name, fontsize=7.5)

        # Line from hub to satellite
        hx = center_x + 1.8 * np.cos(angle)
        hy = center_y + 0.6 * np.sin(angle)
        ax.plot([hx, sx + 0.7], [hy, sy + 0.4], '-', color=C_GREY, lw=1.2, alpha=0.6)

    # Bottom section: drones & database
    draw_rounded_box(ax, 3, 0.3, 3.5, 1.0, color=C_LIGHT, text_color=C_DARK,
                    text='假无人机 / PX4飞控\n（ROS仿真）', fontsize=8, alpha=0.7)
    draw_rounded_box(ax, 7.5, 0.3, 3.5, 1.0, color=C_LIGHT, text_color=C_DARK,
                    text='历史数据库\n（SQLite / PostgreSQL）', fontsize=8, alpha=0.7)

    # Connection lines from bottom satellites to bottom section
    for x_pos, bx in [(4.75, 0.65), (9.25, 9.25)]:
        ax.plot([bx, bx], [1.3, 1.1], '-', color=C_GREY, lw=1, alpha=0.5)
        ax.plot([bx, bx], [1.1, 1.3], '-', color=C_GREY, lw=1, alpha=0.5)

    save_transparent(fig, '04_系统总体架构图.png', dpi=150)


# ═══════════════════════════════════════════════════════════════
# Image 5: 核心数据流全链路时序图
# ═══════════════════════════════════════════════════════════════
def image5_dataflow():
    fig, ax = plt.subplots(figsize=(14, 7))
    ax.set_xlim(0, 14); ax.set_ylim(0, 7)
    ax.axis('off')

    ax.text(7, 6.7, '核心数据流全链路', ha='center', fontsize=15, weight='bold', color=C_DARK)

    # Actors (vertical swimlanes)
    actors = [
        (1.5, '操作人员'),
        (3.3, '中枢\n大模型'),
        (5.1, '离散数据\n翻译模型'),
        (7.0, '边缘执行\n模型'),
        (9.0, '模拟\n无人机'),
        (11.0, '数据监控\n程序'),
        (12.8, '历史\n数据库'),
    ]

    for x, name in actors:
        draw_rounded_box(ax, x-0.65, 5.8, 1.3, 0.6, color=C_SECONDARY,
                        text=name, fontsize=7)
        # Vertical lane line
        ax.plot([x, x], [0.2, 5.7], '-', color=C_GREY, lw=0.8, alpha=0.4)

    # Flows (arrows between swimlanes)
    flows = [
        (1.5, 3.3, 5.2, '1.自然语言任务描述', C_DARK),
        (3.3, 5.1, 4.5, '3.飞行意图（审核后）', C_ACCENT),
        (5.1, 7.0, 3.8, '4.动作编码序列', C_GREEN),
        (7.0, 9.0, 3.1, '5.目标点指令', C_PRIMARY),
        (9.0, 11.0,  2.4, '6.飞行数据流（10Hz）', C_RED),
        (9.0, 12.8, 1.7, '7.轨迹数据归档', C_GREY),
        (11.0, 1.5, 1.0, '8.异常告警', C_RED),
    ]
    # Reverse flows
    flows_r = [
        (3.3, 1.5, 5.2, '2.飞行方案（待审）', C_ACCENT),
        (9.0, 3.3, 4.5, '6b.位姿数据上行', C_PRIMARY),
        (7.0, 5.1, 3.8, '4b.目标点回告', C_GREEN),
    ]

    for x1, x2, y, label, color in flows:
        ax.annotate('', xy=(x2-0.3, y), xytext=(x1+0.3, y),
                   arrowprops=dict(arrowstyle='->', color=color, lw=1.5))
        ax.text((x1+x2)/2, y+0.12, label, ha='center', fontsize=7, color=color)

    for x1, x2, y, label, color in flows_r:
        ax.annotate('', xy=(x1+0.3, y), xytext=(x2-0.3, y),
                   arrowprops=dict(arrowstyle='->', color=color, lw=1.5))
        ax.text((x1+x2)/2, y-0.25, label, ha='center', fontsize=7, color=color)

    save_transparent(fig, '05_核心数据流时序图.png', dpi=150)


# ═══════════════════════════════════════════════════════════════
# Image 6: 单次试飞任务端到端时序图 (Swimlane + timeline)
# ═══════════════════════════════════════════════════════════════
def image6_e2e_timeline():
    fig, ax = plt.subplots(figsize=(14, 9))
    ax.set_xlim(0, 14); ax.set_ylim(0, 9)
    ax.axis('off')

    ax.text(7, 8.7, '单次试飞任务端到端时序', ha='center', fontsize=15,
            weight='bold', color=C_DARK)

    # Participants (horizontal lanes)
    participants = [
        '操作人员',
        '中枢大模型',
        '离散数据翻译模型',
        '边缘执行模型',
        '模拟无人机',
        '监控程序',
    ]
    lane_h = 1.2
    for i, name in enumerate(participants):
        y = 7.5 - i * lane_h
        draw_rounded_box(ax, 0.3, y-0.3, 2.2, 0.9, color=C_SECONDARY,
                        text=name, fontsize=8)
        ax.plot([2.8, 13.7], [y + 0.15, y + 0.15], '-',
                color=C_GREY, lw=0.5, alpha=0.3)

    # Events as labeled boxes in each lane
    events = [
        # (participant_index, time_x, label, color)
        # Lane 0: 操作人员
        (0, 3.0, '发起任务', C_ACCENT),
        (0, 7.5, '审核方案', C_ACCENT),
        (0, 9.5, '批准执行', C_ACCENT),
        (0, 12.5, '响应告警', C_RED),
        # Lane 1: 中枢大模型
        (1, 4.0, '查询场地\n制定方案', C_PRIMARY),
        (1, 8.0, '输出方案\n（待审）', C_PRIMARY),
        (1, 13.0, '分析异常\n生成建议', C_PRIMARY),
        # Lane 2: 离散数据翻译模型
        (2, 10.0, '翻译动作\n编码序列', C_GREEN),
        # Lane 3: 边缘执行模型
        (3, 11.0, '计算目标点', C_SECONDARY),
        # Lane 4: 模拟无人机
        (4, 11.5, '执行飞行\n回传位姿', C_DARK),
        # Lane 5: 监控程序
        (5, 12.0, '检测异常\n触发告警', C_RED),
    ]

    for pid, tx, label, color in events:
        y = 7.5 - pid * lane_h + 0.15
        box_h = 0.8 if '\n' in label else 0.6
        draw_rounded_box(ax, tx-0.7, y-0.3, 1.4, box_h, color=color,
                        text=label, fontsize=7)

    # Vertical message arrows between lanes
    messages = [
        (0, 1, 3.5, '任务描述'),
        (1, 0, 8.0, '方案卡片'),
        (0, 2, 10.0, '批准意图'),
        (2, 3, 10.5, '动作编码'),
        (3, 4, 11.2, '目标点'),
        (4, 5, 11.8, '数据流'),
        (5, 0, 12.3, '告警'),
        (1, 0, 13.0, '处置建议'),
    ]

    for from_p, to_p, tx, label in messages:
        y1 = 7.5 - from_p * lane_h + 0.15
        y2 = 7.5 - to_p * lane_h + 0.15
        color = C_DARK if from_p < to_p else C_RED
        style = 'simple' if from_p < to_p else 'simple'
        ax.annotate('', xy=(tx, y2 - 0.1), xytext=(tx, y1 + 0.1),
                   arrowprops=dict(arrowstyle='->', color=color, lw=1.2))
        mid_y = (y1 + y2) / 2
        ax.text(tx + 0.15, mid_y, label, fontsize=6.5, color=color, va='center')

    # Time axis at bottom
    ax.plot([2.8, 13.5], [0.5, 0.5], 'k-', lw=1.2)
    times = ['T0', 'T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8']
    for i, t in enumerate(times):
        x = 3.0 + i * 1.3
        ax.plot([x, x], [0.4, 0.6], 'k-', lw=0.8)
        ax.text(x, 0.25, t, ha='center', fontsize=7.5, color=C_DARK)

    save_transparent(fig, '06_端到端时序图.png', dpi=150)


# ═══════════════════════════════════════════════════════════════
# Image 7: 前端界面布局图
# ═══════════════════════════════════════════════════════════════
def image7_frontend():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    for ax in [ax1, ax2]:
        ax.set_xlim(0, 10); ax.set_ylim(0, 8)
        ax.axis('off')

    # Left: Desktop layout
    ax1.set_title('电脑版布局', fontsize=13, weight='bold', color=C_DARK, pad=10)

    # Status bar (top)
    draw_rounded_box(ax1, 0.3, 7.2, 9.4, 0.5, color=C_DARK, text='顶部状态栏 (StatusBar)', fontsize=8)

    # Left panel (control)
    draw_rounded_box(ax1, 0.3, 2.0, 3.5, 5.0, color=C_LIGHT, text_color=C_DARK,
                    text='左侧控制面板\n\n· 环境状态（风速/湿度等）\n· 任务进度\n· 状态信息\n· 悬浮球快捷键', fontsize=8)
    # Right panel (main view)
    draw_rounded_box(ax1, 4.1, 2.0, 5.6, 5.0, color=C_LIGHT, text_color=C_DARK,
                    text='右侧主力视图区\n\n· 三维飞行轨迹图（可旋转/缩放）\n· 二维数据图表\n· 视频回传（远期）\n· 数据展示看板', fontsize=8)

    # Center dialogue area
    draw_rounded_box(ax1, 1.5, 1.1, 6.5, 0.7, color=C_SECONDARY,
                    text='对话区：操作人员 ↔ 中枢大模型（文字/语音）', fontsize=7.5)

    # Bottom bar
    draw_rounded_box(ax1, 0.3, 0.2, 9.4, 0.7, color=C_DARK,
                    text='底部任务栏 (BottomBar)：进度 + 紧急中止按钮', fontsize=8)

    # Right: Mobile layout
    ax2.set_title('手机版布局', fontsize=13, weight='bold', color=C_DARK, pad=10)

    # Top: swipable view
    draw_rounded_box(ax2, 0.5, 4.5, 9.0, 3.2, color=C_LIGHT, text_color=C_DARK,
                    text='上栏：可滑动视图区\n\n· 三维轨迹图（默认）  左右滑动切换 →\n· 数据面板  · 图表', fontsize=8)

    # Bottom: dialogue
    draw_rounded_box(ax2, 0.5, 1.5, 9.0, 2.7, color=C_SECONDARY,
                    text='下栏：对话与输入区\n\n· 消息列表\n· 输入框 + 语音按钮\n· 状态信息（下拉展开）', fontsize=7.5)

    # Bottom
    draw_rounded_box(ax2, 0.5, 0.2, 9.0, 1.0, color=C_DARK,
                    text='底部：任务进度 + 悬浮球快捷键 + 紧急中止', fontsize=8)

    fig.suptitle('前端界面布局设计', fontsize=16, weight='bold', color=C_DARK, y=1.02)
    save_transparent(fig, '07_前端界面布局图.png', dpi=150)


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════
if __name__ == '__main__':
    print(f'Generating images to: {OUTDIR}\n')
    image1_structure()
    image2_human_ai()
    image3_roadmap()
    image4_architecture()
    image5_dataflow()
    image6_e2e_timeline()
    image7_frontend()
    print(f'\nAll {7} images generated successfully.')
