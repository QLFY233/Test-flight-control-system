/**
 * HistoryPanels — 历史会话看板数据 (值型, 非坐标图)。
 * 从 store.history.playback.dataset (C1) 渲染:
 *   飞行统计卡片 (时长/里程/最大·平均速度/高度范围/数据点)
 *   + 任务摘要卡片 (名称/状态/动作数 + 回放进度 %)
 * 2026-08-06: 移除高度/速度/加速度/角速度时序折线图 (用户: 历史只显示看板数据, 不要坐标图)。
 */

import store from '../state.js';
import bus from '../event-bus.js';
import { esc } from '../escape.js';

class HistoryPanels {
    constructor() {
        this.container = null;
        this._boundDataset = null;
        this._boundTick = null;
        this._datasetUnsub = null;
        this._tick = 0;
        this._progressEl = null;
    }

    mount(container) {
        this.container = container;
        this._boundDataset = () => this._render();
        this._boundTick = ({ time }) => this._onTick(time);
        this._datasetUnsub = store.subscribe('history.playback.dataset', this._boundDataset);
        bus.on('playback-tick', this._boundTick);
        this._render();
    }

    unmount() {
        if (this._datasetUnsub) { this._datasetUnsub(); this._datasetUnsub = null; }
        if (this._boundTick) { bus.off('playback-tick', this._boundTick); this._boundTick = null; }
        this._progressEl = null;
        this.container = null;
    }

    _render() {
        if (!this.container) return;
        const ds = store.get('history.playback.dataset');

        this.container.innerHTML = `
            <div class="history-panels">
                <div class="history-panels__row">${this._renderStats(ds)}</div>
                <div class="history-panels__row">${this._renderTask(ds)}</div>
            </div>
        `;

        this._progressEl = this.container?.querySelector('[data-role="hp-progress"]');
        this._onTick(store.get('history.playbackTime') || 0);
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
            <div class="history-panels__stats" style="display:flex;flex-wrap:wrap;border:var(--border-hair);background:var(--color-surface);border-radius:var(--radius-md);overflow:hidden;">
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

    /** playback-tick: 任务摘要回放进度刷新。 */
    _onTick(time) {
        this._tick = time || 0;
        if (!this._progressEl) return;
        const ds = store.get('history.playback.dataset');
        const dur = ds?.duration || 0;
        const pct = dur > 0 ? Math.min(100, Math.round((this._tick / dur) * 100)) : 0;
        this._progressEl.textContent = `${pct}%`;
    }
}

export { HistoryPanels };
