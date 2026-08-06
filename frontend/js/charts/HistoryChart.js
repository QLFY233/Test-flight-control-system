/**
 * HistoryChart — Multi-panel history playback.
 * 3 panels: trajectory top-down projection + altitude vs time + speed vs time.
 * Panels linked by time cursor.
 *
 * 2026-08-06 (C7): 数据源改读 store.history.playback.dataset (C1) — 原读实时
 * trajectory.flown 导致选中会话看不到本会话轨迹; 速度直接用遥测 vel 字段 (非位置差分)。
 */

import store from '../state.js';
import bus from '../event-bus.js';

class HistoryChart {
    constructor() {
        this.chart = null;
        this.container = null;
        this._resizeHandler = null;
        this._onSeek = null;
        this._datasetUnsub = null;
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

        this._buildChart();

        this._resizeHandler = () => this.chart && this.chart.resize();
        window.addEventListener('resize', this._resizeHandler);

        // 具名回调引用：unmount 时能真正 off 掉，避免泄漏（bus.on 不返回 unsubscribe）
        this._onSeek = (t) => this._updateTimeCursor(t);
        bus.on('playback-seek', this._onSeek);
        // 数据集变更 (选中新会话) → 重建; 播放推进 → 时间游标
        this._datasetUnsub = store.subscribe('history.playback.dataset', () => this._buildChart());
        this._onTick = () => this._updateTimeCursor(store.get('history.playbackTime') || 0);
        bus.on('playback-tick', this._onTick);
    }

    unmount() {
        if (this._resizeHandler) { window.removeEventListener('resize', this._resizeHandler); this._resizeHandler = null; }
        if (this._onSeek) { bus.off('playback-seek', this._onSeek); this._onSeek = null; }
        if (this._onTick) { bus.off('playback-tick', this._onTick); this._onTick = null; }
        if (this._datasetUnsub) { this._datasetUnsub(); this._datasetUnsub = null; }
        if (this.chart) { this.chart.dispose(); this.chart = null; }
        if (this.container) { this.container.innerHTML = ''; this.container = null; }
    }

    _dataset() {
        return store.get('history.playback.dataset') || { points: [], tStart: 0, tEnd: 0, duration: 0 };
    }

    _buildChart() {
        if (!this.chart || this.chart.isDisposed()) return;

        const ds = this._dataset();
        const points = ds.points || [];
        const tStart = ds.tStart || 0;

        const times = points.map(p => p.t - tStart);
        const altitudes = points.map(p => p.z);
        const trajXY = points.map(p => [p.x, p.y]);
        const speeds = points.map(p => Math.hypot(p.vx, p.vy, p.vz));

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
                // Panel 3: Speed vs time (遥测 vel 模长)
                {
                    name: '速度',
                    type: 'line',
                    xAxisIndex: 2,
                    yAxisIndex: 2,
                    data: times.map((t, i) => [t, speeds[i]]),
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
        const ds = this._dataset();
        const points = ds.points || [];
        const tStart = ds.tStart || 0;
        for (let i = 0; i < points.length; i++) {
            if ((points[i].t - tStart) >= t) return i;
        }
        return points.length - 1;
    }
}

export { HistoryChart };
