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
        this._trajUnsub = null;
        this._droneUnsub = null;
    }

    mount(container) {
        this.container = container;

        const chartEl = document.createElement('div');
        chartEl.style.width = '100%';
        chartEl.style.height = '100%';
        container.appendChild(chartEl);

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

        // Subscribe to trajectory changes (growing during playback) — only update Flown series
        this._trajUnsub = store.subscribe('trajectory', () => {
            this._updateFlownSeries();
        });

        // Subscribe to drone position changes for live marker
        this._droneUnsub = store.subscribe('drone', () => {
            this._updateDroneMarker();
        });
    }

    unmount() {
        if (this._resizeHandler) { window.removeEventListener('resize', this._resizeHandler); this._resizeHandler = null; }
        if (this._updateUnsub) { this._updateUnsub(); this._updateUnsub = null; }
        if (this._trajUnsub) { this._trajUnsub(); this._trajUnsub = null; }
        if (this._droneUnsub) { this._droneUnsub(); this._droneUnsub = null; }
        if (this.chart) { this.chart.dispose(); this.chart = null; }
        if (this.container) { this.container.innerHTML = ''; this.container = null; }
    }

    _buildOption() {
        if (!this.chart || this.chart.isDisposed()) return;

        const field = store.get('field');
        const boundary = field?.boundary || { xMin: 0, xMax: 5, yMin: 0, yMax: 4 };
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
            name: '返航点',
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
                formatter: '返航点',
            },
        }] : [];

        // Planned trajectory (dashed preview)
        const trajectory = store.get('trajectory');
        const plannedData = (trajectory?.planned || []).map(p => [p.x, p.y]);
        const flownData = (trajectory?.flown || []).map(p => [p.x, p.y]);

        const plannedSeries = [
            {
                name: '规划轨迹',
                type: 'line',
                data: plannedData,
                lineStyle: { color: 'rgba(0,188,212,0.35)', type: 'dashed', width: 1, dashOffset: 5 },
                showSymbol: false,
                z: 1,
            },
            {
                name: '已飞轨迹',
                type: 'line',
                data: flownData,
                lineStyle: { color: '#4CAF50', width: 3 },
                showSymbol: false,
                z: 2,
            },
        ];

        // Waypoints
        if (trajectory?.waypoints && trajectory.waypoints.length > 0) {
            plannedSeries.push({
                name: 'Waypoints',
                type: 'scatter',
                data: trajectory.waypoints.map((wp, i) => ({
                    value: [wp.x, wp.y],
                    label: wp.label || String(i + 1),
                })),
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

        // Live drone position marker
        const drone = store.get('drone');
        const dronePos = drone?.position;
        const droneSeries = [{
            name: '无人机',
            type: 'scatter',
            data: dronePos ? [[dronePos.x, dronePos.y]] : [],
            symbolSize: 20,
            symbol: 'pin',
            itemStyle: {
                color: '#FF2A2A',
                borderColor: '#FF6B6B',
                borderWidth: 2,
            },
            label: {
                show: true,
                position: 'right',
                color: '#FF2A2A',
                fontSize: 10,
                formatter: '无人机',
            },
        }];

        this.chart.setOption({
            darkMode: true,
            backgroundColor: 'transparent',
            legend: {
                data: ['无人机', '已飞轨迹', '规划轨迹', '返航点'],
                orient: 'horizontal',
                bottom: 0,
                left: 'center',
                textStyle: { color: '#9E9E9E', fontSize: 10, fontFamily: 'JetBrains Mono, monospace' },
                itemWidth: 16,
                itemHeight: 8,
            },
            toolbox: {
                feature: {
                    restore: {},
                },
                top: 4,
                right: 10,
                iconStyle: { borderColor: '#9E9E9E' },
            },
            grid: {
                top: 36,
                right: 16,
                bottom: 40,
                left: 44,
                containLabel: true,
            },
            xAxis: {
                type: 'value',
                name: 'X (m)',
                nameLocation: 'center',
                nameGap: 20,
                min: (boundary?.xMin ?? 0) - 1,
                max: (boundary?.xMax ?? 5) + 1,
                axisLine: { lineStyle: { color: '#2A2A2A' } },
                axisLabel: { color: '#616161', fontSize: 10 },
                splitLine: { lineStyle: { color: '#1A1A1A' } },
            },
            yAxis: {
                type: 'value',
                name: 'Y (m)',
                nameLocation: 'center',
                nameGap: 24,
                min: (boundary?.yMin ?? 0) - 1,
                max: (boundary?.yMax ?? 4) + 1,
                axisLine: { lineStyle: { color: '#2A2A2A' } },
                axisLabel: { color: '#616161', fontSize: 10 },
                splitLine: { lineStyle: { color: '#1A1A1A' } },
            },
            series: [
                ...homeSeries,
                ...obstacleSeries,
                ...plannedSeries,
                ...droneSeries,
            ],
            animation: true,
            animationDuration: 400,
        });
    }

    _updateDroneMarker() {
        if (!this.chart || this.chart.isDisposed()) return;
        const drone = store.get('drone');
        const trajectory = store.get('trajectory');
        const pos = drone?.position;
        const flown = (trajectory?.flown || []).map(p => [p.x, p.y]);
        this.chart.setOption({
            animation: false,
            animationDuration: 0,
            animationDurationUpdate: 0,
            series: [
                { name: '无人机', data: pos ? [[pos.x, pos.y]] : [] },
                { name: '已飞轨迹', data: flown },
            ],
        }, { notMerge: false });
    }

    _updateFlownSeries() {
        // Combined with drone update in _updateDroneMarker
        this._updateDroneMarker();
    }
}

export { FieldMap2D };
