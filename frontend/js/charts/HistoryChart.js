/**
 * HistoryChart — Multi-panel history playback.
 * 3 panels: trajectory top-down projection + altitude vs time + velocity vs time.
 * Panels linked by time cursor.
 */

import store from '../state.js';
import bus from '../event-bus.js';

class HistoryChart {
    constructor() {
        this.chart = null;
        this.container = null;
        this._resizeHandler = null;
        this._timeUnsub = null;
        this._playbackUnsub = null;
        this._trajectoryUnsub = null;
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

        this._buildChart();

        this._resizeHandler = () => this.chart && this.chart.resize();
        window.addEventListener('resize', this._resizeHandler);

        // Listen for time cursor updates
        this._timeUnsub = bus.on('playback-seek', (t) => this._updateTimeCursor(t));
        this._playbackUnsub = bus.on('playback-state-changed', () => {});
        this._trajectoryUnsub = store.subscribe('trajectory', () => this._buildChart());
    }

    unmount() {
        if (this._resizeHandler) { window.removeEventListener('resize', this._resizeHandler); this._resizeHandler = null; }
        if (this._timeUnsub) { bus.off('playback-seek', this._timeUnsub); this._timeUnsub = null; }
        if (this._playbackUnsub) { bus.off('playback-state-changed', this._playbackUnsub); this._playbackUnsub = null; }
        if (this._trajectoryUnsub) { this._trajectoryUnsub(); this._trajectoryUnsub = null; }
        if (this.chart) { this.chart.dispose(); this.chart = null; }
        if (this.container) { this.container.innerHTML = ''; this.container = null; }
    }

    _buildChart() {
        if (!this.chart || this.chart.isDisposed()) return;

        const trajectory = store.get('trajectory');
        const flown = trajectory?.flown || [];

        const times = flown.map(p => p.t != null ? p.t : 0);
        const altitudes = flown.map(p => (p.z != null ? p.z : p.y));
        const trajXY = flown.map(p => [p.x, p.y]);

        // Compute velocity from position deltas
        const velocities = [];
        for (let i = 1; i < flown.length; i++) {
            const dx = flown[i].x - flown[i - 1].x;
            const dy = flown[i].y - flown[i - 1].y;
            const dz = (flown[i].z || flown[i].y) - (flown[i - 1].z || flown[i - 1].y);
            const dt = (flown[i].t || i) - (flown[i - 1].t || (i - 1));
            const speed = dt > 0 ? Math.sqrt(dx * dx + dy * dy + dz * dz) / dt : 0;
            velocities.push([times[i] || i, speed]);
        }

        this.chart.setOption({
            darkMode: true,
            backgroundColor: 'transparent',
            tooltip: {
                trigger: 'axis',
                axisPointer: {
                    type: 'cross',
                    link: [{ xAxisIndex: 'all' }],
                    label: { backgroundColor: '#333' },
                },
            },
            grid: [
                { top: 30, left: 60, right: 20, bottom: '60%', height: '35%' },
                { top: '45%', left: 60, right: 20, bottom: '30%', height: '20%' },
                { top: '72%', left: 60, right: 20, bottom: 10, height: '20%' },
            ],
            xAxis: [
                { gridIndex: 0, type: 'value', name: 'X (m)', nameTextStyle: { color: '#616161' }, axisLine: { lineStyle: { color: '#2A2A2A' } }, axisLabel: { color: '#616161', fontSize: 9 } },
                { gridIndex: 1, type: 'value', name: 'Time (s)', nameTextStyle: { color: '#616161' }, axisLine: { lineStyle: { color: '#2A2A2A' } }, axisLabel: { color: '#616161', fontSize: 9 }, show: true },
                { gridIndex: 2, type: 'value', name: 'Time (s)', nameTextStyle: { color: '#616161' }, axisLine: { lineStyle: { color: '#2A2A2A' } }, axisLabel: { color: '#616161', fontSize: 9 }, show: true },
            ],
            yAxis: [
                { gridIndex: 0, type: 'value', name: 'Y (m)', nameTextStyle: { color: '#616161' }, axisLine: { lineStyle: { color: '#2A2A2A' } }, axisLabel: { color: '#616161', fontSize: 9 }, splitLine: { lineStyle: { color: '#1A1A1A' } } },
                { gridIndex: 1, type: 'value', name: 'Alt (m)', nameTextStyle: { color: '#616161' }, axisLine: { lineStyle: { color: '#2A2A2A' } }, axisLabel: { color: '#616161', fontSize: 9 }, splitLine: { lineStyle: { color: '#1A1A1A' } } },
                { gridIndex: 2, type: 'value', name: 'Speed (m/s)', nameTextStyle: { color: '#616161' }, axisLine: { lineStyle: { color: '#2A2A2A' } }, axisLabel: { color: '#616161', fontSize: 9 }, splitLine: { lineStyle: { color: '#1A1A1A' } } },
            ],
            series: [
                // Panel 1: Top-down trajectory
                {
                    name: '轨迹',
                    type: 'line',
                    xAxisIndex: 0,
                    yAxisIndex: 0,
                    data: trajXY,
                    lineStyle: { color: '#4CAF50', width: 2 },
                    showSymbol: false,
                },
                // Panel 2: Altitude vs time
                {
                    name: '高度',
                    type: 'line',
                    xAxisIndex: 1,
                    yAxisIndex: 1,
                    data: times.map((t, i) => [t, altitudes[i]]),
                    lineStyle: { color: '#00BCD4', width: 1.5 },
                    showSymbol: false,
                },
                // Panel 3: Velocity vs time
                {
                    name: '速度',
                    type: 'line',
                    xAxisIndex: 2,
                    yAxisIndex: 2,
                    data: velocities,
                    lineStyle: { color: '#FFC107', width: 1.5 },
                    showSymbol: false,
                },
            ],
            animation: false,
        });
    }

    _updateTimeCursor(t) {
        if (!this.chart || this.chart.isDisposed()) return;

        this.chart.dispatchAction({
            type: 'showTip',
            seriesIndex: 0,
            dataIndex: this._findIndex(t),
        });
    }

    _findIndex(t) {
        const trajectory = store.get('trajectory');
        const flown = trajectory?.flown || [];
        for (let i = 0; i < flown.length; i++) {
            if ((flown[i].t || i) >= t) return i;
        }
        return flown.length - 1;
    }
}

export { HistoryChart };
