/**
 * FieldMap2D — Top-down field view for Beta page.
 * Shows boundary rectangle, obstacle projections, home marker.
 * Supports zoom, pan, and click to select reference point.
 */

import store from '../state.js';
import bus from '../event-bus.js';

class FieldMap2D {
    constructor() {
        this.chart = null;
        this.container = null;
        this._resizeHandler = null;
        this._updateUnsub = null;
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

        // Subscribe to field changes
        this._updateUnsub = store.subscribe('field', () => {
            this._buildOption();
        });
    }

    unmount() {
        if (this._resizeHandler) { window.removeEventListener('resize', this._resizeHandler); this._resizeHandler = null; }
        if (this._updateUnsub) { this._updateUnsub(); this._updateUnsub = null; }
        if (this.chart) { this.chart.dispose(); this.chart = null; }
        if (this.container) { this.container.innerHTML = ''; this.container = null; }
    }

    _buildOption() {
        if (!this.chart || this.chart.isDisposed()) return;

        const field = store.get('field');
        const boundary = field?.boundary || { xMin: -50, xMax: 50, yMin: -50, yMax: 50 };
        // obstacles 预编已废弃 (schema_version=2, 阶段2/4 改雷达在线感知); 保留兼容但不作为主要渲染
        const obstacles = field?.obstacles || [];
        const home = field?.home;

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

        // Planned trajectory
        const trajectory = store.get('trajectory');
        const plannedSeries = [];
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
        const actionSeq = trajectory?.actionSequence || [];
        if (actionSeq.length > 0) {
            const wpData = actionSeq
                .filter(a => a.params?.target)
                .map((a, i) => ({
                    value: [a.params.target.x ?? 0, a.params.target.y ?? 0],
                    label: a.code || String(i + 1),
                }));
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
            ],
            animation: true,
            animationDuration: 400,
        });
    }
}

export { FieldMap2D };
