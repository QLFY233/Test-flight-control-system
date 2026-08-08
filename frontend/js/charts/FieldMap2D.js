/**
 * FieldMap2D — Top-down field view for Beta page.
 * Shows boundary rectangle, obstacle projections, home marker.
 * Supports zoom, pan, and click to select reference point.
 *
 * 2026-08-06: 新增 history 模式 — 渲染选中历史任务轨迹 (history.playback.dataset)
 * + 回放游标, 随 playback-tick 移动; 不污染实时数据。
 */

import store from '../state.js';
import bus from '../event-bus.js';

class FieldMap2D {
    constructor(mode = 'live') {
        this.mode = mode;
        this.chart = null;
        this.container = null;
        this._resizeHandler = null;
        this._updateUnsub = null;
        this._trajUnsub = null;   // trajectory 变更 → 重建 (计划/轨迹线)
        this._droneUnsub = null;  // drone 变更 → 无人机标记增量更新 (10Hz)
        this._datasetUnsub = null; // history 模式: 数据集变更 → 重建
        this._tickHandler = null;  // history 模式: playback-tick → 游标移动
    }

    mount(container) {
        this.container = container;

        const chartEl = document.createElement('div');
        chartEl.style.width = '100%';
        chartEl.style.height = '100%';
        container.appendChild(chartEl);

        if (typeof echarts === 'undefined') {
            chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--color-text-disabled);font-size:var(--text-sm);">ECharts 加载失败（CDN 不可达）</div>';
            return;
        }

        this.chart = echarts.init(chartEl, null, {
            backgroundColor: 'transparent',
        });

        this._buildOption();
        // field 配置通常在页面初始化后异步到达，ECharts 首次可能使用默认范围。
        // 移到布局完成后的下一帧再按容器尺寸刷新；旧 dataZoom 缩放由 setOption notMerge 重置。
        requestAnimationFrame(() => this.chart?.resize({ animation: { duration: 0 } }));
        this._resizeHandler = () => this.chart && this.chart.resize();
        window.addEventListener('resize', this._resizeHandler);

        // Click to select reference point
        this.chart.on('click', (params) => {
            if (params.componentType === 'grid' || params.componentType === 'series') {
                const x = params.value?.[0] ?? params.data?.[0];
                const y = params.value?.[1] ?? params.data?.[1];
                if (x != null && y != null) {
                    bus.emit('fieldmap-click', { x, y });
                }
            }
        });

        // Subscribe to field changes (global 场地配置, 两种模式共用)
        this._updateUnsub = store.subscribe('field', () => {
            this._buildOption();
        });

        if (this.mode === 'history') {
            // 历史模式: 数据集变更 → 重建轨迹; playback-tick → 回放游标移动
            this._datasetUnsub = store.subscribe('history.playback.dataset', () => {
                this._buildOption();
            });
            this._tickHandler = () => this._updateHistoryMarker();
            bus.on('playback-tick', this._tickHandler);
        } else {
            // 计划/已飞轨迹更新 → 整图重建 (低频, 对齐 field 模式)
            this._trajUnsub = store.subscribe('trajectory', () => {
                this._buildOption();
            });
            // 无人机位置 10Hz → 仅增量更新标记 series, 不重建整图
            this._droneUnsub = store.subscribe('drone', () => {
                this._updateDroneMarker();
            });
        }
    }

    unmount() {
        if (this._resizeHandler) { window.removeEventListener('resize', this._resizeHandler); this._resizeHandler = null; }
        if (this._updateUnsub) { this._updateUnsub(); this._updateUnsub = null; }
        if (this._trajUnsub) { this._trajUnsub(); this._trajUnsub = null; }
        if (this._droneUnsub) { this._droneUnsub(); this._droneUnsub = null; }
        if (this._datasetUnsub) { this._datasetUnsub(); this._datasetUnsub = null; }
        if (this._tickHandler) { bus.off('playback-tick', this._tickHandler); this._tickHandler = null; }
        if (this.chart) { this.chart.dispose(); this.chart = null; }
        if (this.container) { this.container.innerHTML = ''; this.container = null; }
    }

    // 历史回放游标: 当前帧位置 (playback-tick 增量更新, 固定 id 合并)
    _updateHistoryMarker() {
        if (!this.chart || this.chart.isDisposed()) return;
        const ds = store.get('history.playback.dataset');
        const pts = ds?.points || [];
        const idx = store.get('history.playback.index') || 0;
        const p = pts[idx];
        const data = (p && p.x != null && p.y != null) ? [[p.x, p.y]] : [];
        this.chart.setOption({ series: [{ id: 'fieldmap-playback', data }] });
    }

    // 无人机位置标记: 10Hz 增量更新 (series 固定 id, ECharts 按 id 合并)
    _updateDroneMarker() {
        if (!this.chart || this.chart.isDisposed()) return;
        const p = store.get('drone')?.position;
        const data = (p && p.x != null && p.y != null) ? [[p.x, p.y]] : [];
        this.chart.setOption({ series: [{ id: 'fieldmap-drone', data }] });
    }

    // 目标点统一解析: 优先归一化 goal ({x,y,z}), 兜底 a.target (数组) / a.params.target (对象)
    _toXYZ(t) {
        if (!t) return null;
        if (Array.isArray(t) && t.length >= 3) return { x: t[0], y: t[1], z: t[2] };
        if (typeof t === 'object') return { x: t.x ?? 0, y: t.y ?? 0, z: t.z ?? 0 };
        return null;
    }

    _buildOption() {
        if (!this.chart || this.chart.isDisposed()) return;

        const field = store.get('field');
        const rawB = field?.boundary;
        // 兼容 {x:[min,max],y:[min,max],z:[min,max]} 与旧 {xMin,xMax,...} 两种格式
        const boundary = (rawB && Array.isArray(rawB.x))
            ? { xMin: rawB.x[0], xMax: rawB.x[1], yMin: rawB.y[0], yMax: rawB.y[1], zMin: rawB.z[0], zMax: rawB.z[1] }
            : (rawB || { xMin: -50, xMax: 50, yMin: -50, yMax: 50 });
        // obstacles 预编已废弃 (schema_version=2, 阶段2/4 改雷达在线感知); 保留兼容但不作为主要渲染
        const obstacles = field?.obstacles || [];
        // HOME 兼容 {position:[x,y,z]} 与旧 {x,y,z} 两种格式
        const rawHome = field?.home;
        const home = (rawHome && Array.isArray(rawHome.position))
            ? { x: rawHome.position[0], y: rawHome.position[1], z: rawHome.position[2], yaw: rawHome.yaw || 0 }
            : (rawHome || null);

        // Build series for each obstacle (as scatter or custom)
        const obstacleSeries = obstacles.map((obs, i) => {
            const pos = obs.position || { x: 0, y: 0, z: 0 };
            const size = obs.size || {};
            const w = (size.width || size.radius * 2 || 2) / 2;
            const h = (size.depth || size.radius * 2 || 2) / 2;

            return {
                name: `障碍 ${i + 1}`,
                type: 'scatter',
                data: [[pos.x, pos.y]],
                symbolSize: Math.max(w * 2, h * 2) * 2,
                symbol: 'rect',
                itemStyle: {
                    color: 'rgba(255, 193, 7, 0.3)',
                    borderColor: 'rgba(255, 143, 0, 0.6)',
                    borderWidth: 1,
                },
                markArea: {
                    silent: true,
                    data: [[
                        { xAxis: pos.x - w, yAxis: pos.y - h },
                        { xAxis: pos.x + w, yAxis: pos.y + h },
                    ]],
                    itemStyle: {
                        color: 'rgba(255, 193, 7, 0.15)',
                        borderColor: 'rgba(255, 143, 0, 0.3)',
                        borderWidth: 1,
                    },
                },
            };
        });

        // Home marker
        const homeSeries = home ? [{
            name: 'Home',
            type: 'scatter',
            data: [[home.x, home.y]],
            symbolSize: 16,
            symbol: 'diamond',
            itemStyle: {
                color: 'rgba(76, 175, 80, 0.8)',
                borderColor: '#4CAF50',
                borderWidth: 2,
            },
            label: {
                show: true,
                position: 'top',
                color: '#4CAF50',
                fontSize: 11,
                formatter: 'HOME',
            },
        }] : [];

        // 数据源: live 读实时 store.trajectory; history 读回放数据集 (匹配选中历史任务)
        const trajectory = this.mode === 'history' ? null : (store.get('trajectory') || {});
        const plannedSeries = [];

        if (this.mode === 'history') {
            // 历史任务轨迹 (完整 XY 路径, 数据来自选中任务的遥测)
            const ds = store.get('history.playback.dataset');
            const pts = ds?.points || [];
            if (pts.length > 1) {
                plannedSeries.push({
                    name: 'HistoryFlown',
                    type: 'line',
                    data: pts.map(p => [p.x, p.y]),
                    lineStyle: { color: '#4CAF50', width: 2 },
                    showSymbol: false,
                });
            }
        } else {
            // 待批准预览 (黄色): β 提议预翻译 (store.trajectory.pending), 批准后由 alpha_output 清空
            const pending = trajectory?.pending || null;
            if (pending?.planned && pending.planned.length > 1) {
                plannedSeries.push({
                    name: 'PendingPlan',
                    type: 'line',
                    data: pending.planned.map(p => [p.x, p.y]),
                    lineStyle: {
                        color: '#FFC107',
                        type: 'dashed',
                        width: 1.5,
                    },
                    showSymbol: false,
                });
            }
            if (pending?.seq) {
                const pWp = pending.seq
                    .filter(a => a.goal && a.goal.x != null && a.goal.y != null)
                    .map(a => ({ value: [a.goal.x, a.goal.y], label: (a.code || 'act') + '?' }));
                if (pWp.length > 0) {
                    plannedSeries.push({
                        name: 'PendingWaypoints',
                        type: 'scatter',
                        data: pWp,
                        symbolSize: 7,
                        symbol: 'circle',
                        itemStyle: {
                            color: '#FFB300',
                            borderColor: '#FFD54F',
                            borderWidth: 1.5,
                        },
                        label: {
                            show: true,
                            position: 'top',
                            color: '#FFB300',
                            fontSize: 9,
                            formatter: (p) => p.data.label,
                        },
                    });
                }
            }

            if (trajectory?.planned && trajectory.planned.length > 1) {
                plannedSeries.push({
                    name: 'Planned',
                    type: 'line',
                    data: trajectory.planned.map(p => [p.x, p.y]),
                    lineStyle: {
                        color: '#00BCD4',
                        type: 'dashed',
                        width: 1.5,
                    },
                    showSymbol: false,
                });
            }

            // Flown trajectory
            if (trajectory?.flown && trajectory.flown.length > 1) {
                plannedSeries.push({
                    name: 'Flown',
                    type: 'line',
                    data: trajectory.flown.map(p => [p.x, p.y]),
                    lineStyle: {
                        color: '#4CAF50',
                        width: 2,
                    },
                    showSymbol: false,
                });
            }

            // ActionSequence waypoints (schema_version=2: 使用 actionSequence 替代旧 waypoints)
            // 目标点优先取归一化 a.goal; 兼容旧格式 a.target(数组 [x,y,z]) / a.params.target(对象)
            const actionSeq = trajectory?.actionSequence || [];
            const wpData = [];
            if (actionSeq.length > 0) {
                actionSeq.forEach((a, i) => {
                    const g = a.goal ?? this._toXYZ(a.target) ?? this._toXYZ(a.params && a.params.target);
                    if (!g) return;   // hover/yaw 等无目标动作跳过
                    wpData.push({ value: [g.x, g.y], label: a.code || String(i + 1) });
                });
            }
            if (wpData.length > 0) {
                plannedSeries.push({
                    name: 'Waypoints',
                    type: 'scatter',
                    data: wpData,
                    symbolSize: 8,
                    symbol: 'circle',
                    itemStyle: {
                        color: '#00BCD4',
                        borderColor: '#4DD0E1',
                        borderWidth: 2,
                    },
                    label: {
                        show: true,
                        position: 'top',
                        color: '#9E9E9E',
                        fontSize: 10,
                        formatter: (p) => p.data.label,
                    },
                });
            }
        }

        this.chart.setOption({
            darkMode: true,
            backgroundColor: 'transparent',
            toolbox: {
                feature: {
                    dataZoom: {},
                    restore: {},
                },
                top: 4,
                right: 10,
                iconStyle: { borderColor: '#9E9E9E' },
            },
            grid: {
                top: 40,
                right: 20,
                bottom: 30,
                left: 50,
            },
            xAxis: {
                type: 'value',
                name: 'X (m)',
                min: boundary?.xMin ?? -50,
                max: boundary?.xMax ?? 50,
                axisLine: { lineStyle: { color: '#2A2A2A' } },
                axisLabel: { color: '#616161', fontSize: 10 },
                splitLine: { lineStyle: { color: '#1A1A1A' } },
            },
            yAxis: {
                type: 'value',
                name: 'Y (m)',
                min: boundary?.yMin ?? -50,
                max: boundary?.yMax ?? 50,
                axisLine: { lineStyle: { color: '#2A2A2A' } },
                axisLabel: { color: '#616161', fontSize: 10 },
                splitLine: { lineStyle: { color: '#1A1A1A' } },
            },
            dataZoom: [{
                type: 'inside',
                xAxisIndex: 0,
            }, {
                type: 'inside',
                yAxisIndex: 0,
            }],
            series: [
                ...homeSeries,
                ...obstacleSeries,
                ...plannedSeries,
                // 实时模式: 无人机当前位置标记 (青色; id 固定供 _updateDroneMarker 增量更新)
                // 历史模式: 回放游标 (红色; id 固定供 _updateHistoryMarker 增量更新)
                this.mode === 'history'
                    ? {
                        id: 'fieldmap-playback',
                        name: 'Playback',
                        type: 'scatter',
                        data: (() => {
                            const ds = store.get('history.playback.dataset');
                            const p = ds?.points?.[store.get('history.playback.index') || 0];
                            return (p && p.x != null && p.y != null) ? [[p.x, p.y]] : [];
                        })(),
                        symbolSize: 10,
                        symbol: 'circle',
                        itemStyle: {
                            color: '#FF2A2A',
                            borderColor: '#FF8A80',
                            borderWidth: 1.5,
                        },
                        z: 10,
                    }
                    : {
                        id: 'fieldmap-drone',
                        name: 'Drone',
                        type: 'scatter',
                        data: (() => {
                            const p = store.get('drone')?.position;
                            return (p && p.x != null && p.y != null) ? [[p.x, p.y]] : [];
                        })(),
                        symbolSize: 10,
                        symbol: 'circle',
                        itemStyle: {
                            color: '#00BCD4',
                            borderColor: '#4DD0E1',
                            borderWidth: 1,
                        },
                        z: 10,
                    },
            ],
            animation: true,
            animationDuration: 400,
        }, { notMerge: true });
    }
}

export { FieldMap2D };
