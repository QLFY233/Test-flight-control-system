/**
 * HistoryPanels — 历史会话看板式数据面板。
 * 从 store.history.playback.dataset (C1) 渲染:
 *   高度 / 速度三维 / 加速度 / 角速度 时序折线图 (ECharts)
 *   + 飞行统计卡片 (时长/里程/最大/平均速度/高度范围)
 *   + 任务摘要卡片 (状态/动作数/回放进度)
 * 订阅 playback-tick (C2) 在折线图上叠加时间游标。
 */

import store from '../state.js';
import bus from '../event-bus.js';
import { esc } from '../escape.js';

// 图表降采样上限 (10000 点 → ≤600 点, 渲染流畅)
const MAX_SERIES_POINTS = 600;

// 面板规格: key=数据集字段, series=[字段, 中文名, 颜色]
const PANEL_SPECS = [
    { key: 'altitude', title: 'ALTITUDE · 高度', unit: 'm', series: [['z', 'Z', '#FF2A2A']] },
    { key: 'velocity', title: 'VELOCITY · 速度三维', unit: 'm/s', series: [['vx', 'VX', '#FF2A2A'], ['vy', 'VY', '#4AF626'], ['vz', 'VZ', '#FFB300']] },
    { key: 'accel', title: 'ACCEL · 加速度', unit: 'm/s²', series: [['ax', 'AX', '#FF2A2A'], ['ay', 'AY', '#4AF626'], ['az', 'AZ', '#FFB300']] },
    { key: 'angular', title: 'ANGULAR · 角速度', unit: 'rad/s', series: [['wx', 'WX', '#FF2A2A'], ['wy', 'WY', '#4AF626'], ['wz', 'WZ', '#FFB300']] },
];

// 数据降采样: 保留首尾, 中间按步长取样
function _sample(points) {
    if (points.length <= MAX_SERIES_POINTS) return points;
    const step = Math.ceil(points.length / MAX_SERIES_POINTS);
    return points.filter((_, i) => i % step === 0);
}

class HistoryPanels {
    constructor() {
        this.container = null;
        this.charts = new Map();   // key -> echarts 实例
        this._resizeHandler = null;
        this._boundDataset = null;
        this._boundTick = null;
        this._datasetUnsub = null;
        this._tick = 0;
        this._progressEl = null;
    }

    mount(container) {
        this.container = container;
        this._resizeHandler = () => this.charts.forEach(c => c.resize());
        window.addEventListener('resize', this._resizeHandler);

        // 数据集变化 → 整网格重建; playback-tick → 游标 + 进度刷新
        this._boundDataset = () => this._render();
        this._boundTick = ({ time, index }) => this._onTick(time, index);
        this._datasetUnsub = store.subscribe('history.playback.dataset', this._boundDataset);
        bus.on('playback-tick', this._boundTick);

        this._render();
    }

    unmount() {
        if (this._resizeHandler) { window.removeEventListener('resize', this._resizeHandler); this._resizeHandler = null; }
        if (this._datasetUnsub) { this._datasetUnsub(); this._datasetUnsub = null; }
        if (this._boundTick) { bus.off('playback-tick', this._boundTick); this._boundTick = null; }
        this.charts.forEach(c => c.dispose());
        this.charts.clear();
        this._progressEl = null;
        this.container = null;
    }

    _render() {
        if (!this.container) return;
        const ds = store.get('history.playback.dataset');
        const points = ds?.points || [];

        // 清空旧的 echarts 实例
        this.charts.forEach(c => c.dispose());
        this.charts.clear();

        this.container.innerHTML = `
            <div class="history-panels">
                <div class="history-panels__row">${this._renderStats(ds)}</div>
                <div class="history-panels__row">${this._renderTask(ds)}</div>
                <div class="history-panels__grid">${PANEL_SPECS.map(s => this._panelHtml(s)).join('')}</div>
            </div>
        `;

        PANEL_SPECS.forEach(spec => {
            const el = this.container?.querySelector(`#hp-${spec.key}`);
            if (!el || typeof echarts === 'undefined') return;
            const chart = echarts.init(el);
            this.charts.set(spec.key, chart);
            chart.setOption(this._buildOption(spec, ds));
        });

        this._progressEl = this.container?.querySelector('[data-role="hp-progress"]');
        this._onTick(store.get('history.playbackTime') || 0, store.get('history.playback.index') || 0);
    }

    _panelHtml(spec) {
        return `
            <div class="history-panel" style="border:var(--border-hair);background:var(--color-surface);border-radius:var(--radius-md);display:flex;flex-direction:column;min-height:180px;overflow:hidden;">
                <div style="padding:6px 10px;font-family:var(--font-mono);font-size:var(--text-2xs);letter-spacing:var(--track-wide);color:var(--color-text-disabled);border-bottom:var(--border-hair);">
                    ${esc(spec.title)}
                </div>
                <div id="hp-${spec.key}" style="flex:1;min-height:140px;"></div>
            </div>
        `;
    }

    _buildOption(spec, ds) {
        const points = _sample(ds?.points || []);
        const tStart = ds?.tStart || 0;
        const timeAxis = (field) => points.map(p => [p.t - tStart, p[field]]);
        return {
            backgroundColor: 'transparent',
            grid: { left: '12%', right: '6%', top: '12%', bottom: '12%' },
            textStyle: { color: '#AAAAAA', fontSize: 10 },
            tooltip: { trigger: 'axis' },
            xAxis: { type: 'value', name: 't(s)', nameTextStyle: { fontSize: 9, color: '#AAAAAA' }, axisLabel: { color: '#888888', fontSize: 9 }, splitLine: { lineStyle: { color: '#1C1C1C' } } },
            yAxis: { type: 'value', name: spec.unit, nameTextStyle: { fontSize: 9, color: '#AAAAAA' }, axisLabel: { color: '#888888', fontSize: 9 }, splitLine: { lineStyle: { color: '#1C1C1C' } } },
            series: spec.series.map(([field, label, color], i) => ({
                type: 'line',
                name: label,
                data: timeAxis(field),
                symbol: 'none',
                lineStyle: { color, width: 1 },
                itemStyle: { color },
            })),
            legend: { textStyle: { color: '#AAAAAA', fontSize: 9 }, itemWidth: 10, itemHeight: 6, top: 2, right: 4 },
            animation: false,
        };
    }

    _renderStats(ds) {
        const pts = ds?.points || [];
        let distance = 0, horizontal = 0, vmax = 0, vsum = 0, vcount = 0;
        let zmin = Infinity, zmax = -Infinity;
        for (let i = 0; i < pts.length; i++) {
            const p = pts[i];
            const z = p.z;
            if (z < zmin) zmin = z;
            if (z > zmax) zmax = z;
            const sp = Math.hypot(p.vx, p.vy, p.vz);
            if (sp > vmax) vmax = sp;
            vsum += sp; vcount++;
            if (i > 0) {
                const prev = pts[i - 1];
                distance += Math.hypot(p.x - prev.x, p.y - prev.y, p.z - prev.z);
                horizontal += Math.hypot(p.x - prev.x, p.y - prev.y);
            }
        }
        const dur = ds?.duration || 0;
        const stat = (label, val) => `
            <div style="flex:1;min-width:0;padding:var(--space-2) var(--space-3);border-right:var(--border-hair);">
                <div style="font-family:var(--font-mono);font-size:var(--text-2xs);letter-spacing:var(--track-wide);color:var(--color-text-disabled);">${esc(label)}</div>
                <div style="font-family:var(--font-mono);font-size:var(--font-md);font-weight:600;color:var(--color-text);margin-top:2px;">${esc(val)}</div>
            </div>`;
        const fmt = (n, d = 1) => (Number.isFinite(n) ? n.toFixed(d) : '--');
        return `
            <div class="history-panels__stats" style="display:flex;border:var(--border-hair);background:var(--color-surface);border-radius:var(--radius-md);overflow:hidden;">
                ${stat('时长', fmt(dur) + 's')}
                ${stat('里程', fmt(distance) + 'm')}
                ${stat('最大速度', fmt(vmax) + 'm/s')}
                ${stat('平均速度', fmt(vcount ? vsum / vcount : 0) + 'm/s')}
                ${stat('高度范围', (Number.isFinite(zmin) ? fmt(zmin) : '--') + '~' + (Number.isFinite(zmax) ? fmt(zmax) : '--') + 'm')}
                ${stat('数据点', String(pts.length))}
            </div>
        `;
    }

    _renderTask(ds) {
        const info = ds?.taskInfo || {};
        const status = info.status || 'idle';
        return `
            <div class="history-panels__task" style="display:flex;align-items:center;gap:var(--space-3);padding:var(--space-2) var(--space-3);border:var(--border-hair);background:var(--color-surface);border-radius:var(--radius-md);">
                <span style="font-family:var(--font-mono);font-size:var(--text-2xs);letter-spacing:var(--track-wide);color:var(--color-text-disabled);">TASK</span>
                <span style="font-size:var(--font-sm);font-weight:600;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${esc(info.name || '--')}</span>
                <span style="font-size:var(--font-sm);color:var(--color-text-secondary);">状态 ${esc(status)}</span>
                <span style="font-size:var(--font-sm);color:var(--color-text-secondary);">动作 ${info.totalActions ?? 0}</span>
                <span style="font-size:var(--font-sm);color:var(--color-text-secondary);">数据 ${info.telemetryCount ?? 0} 点</span>
                <span style="margin-left:auto;font-family:var(--font-mono);font-size:var(--font-md);font-weight:600;color:var(--color-blue);" data-role="hp-progress">0%</span>
            </div>
        `;
    }

    /**
     * playback-tick: 折线图叠加时间游标 + 任务摘要进度刷新。
     */
    _onTick(time, index) {
        this._tick = time || 0;
        const relT = this._tick;   // 引擎推进的 time 为相对秒 (0..duration), 与图表 x 轴同刻度
        this.charts.forEach((chart, key) => {
            if (chart.isDisposed()) return;
            const seriesCount = (PANEL_SPECS.find(s => s.key === key)?.series || []).length;
            chart.setOption({
                series: Array.from({ length: seriesCount }, () => ({
                    markLine: {
                        symbol: 'none',
                        data: [{ xAxis: relT }],
                        lineStyle: { color: '#888', type: 'dashed', width: 1 },
                        label: { show: false },
                        silent: true,
                    },
                })),
            }, { lazyUpdate: true });
        });

        // 任务摘要: 回放进度
        if (this._progressEl) {
            const ds = store.get('history.playback.dataset');
            const dur = ds?.duration || 0;
            const pct = dur > 0 ? Math.min(100, Math.round((this._tick / dur) * 100)) : 0;
            this._progressEl.textContent = `${pct}%`;
        }
    }
}

export { HistoryPanels };
