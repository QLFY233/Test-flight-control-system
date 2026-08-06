/**
 * TimelineControl — History playback controls.
 * Play/pause, step, seek bar, speed selector.
 *
 * 2026-08-06 (C6): 时长改从 history.playback.dataset.duration (修恒 60s bug);
 * 订阅 playback-tick 增量更新 seek/时间/进度 (播放时不再停滞);
 * 进度条 = range 轨道填充 (读作进度条, 仍可拖拽 seek) + 百分比;
 * 任务动作指示 (动作 X/Y · 状态) 从数据集 taskInfo 真实计算。
 */

import store from '../state.js';
import bus from '../event-bus.js';

class TimelineControl {
    constructor(container) {
        this.container = container;
        this._timeEl = null;
        this._seekEl = null;
        this._pctEl = null;
        this._taskEl = null;
        this._playBtnEl = null;
        this._datasetUnsub = null;
        this._boundTick = null;
    }

    mount() {
        this.render();
        // 数据集变更 → 重渲染 (新会话新时长); playback-tick → 增量更新显示
        this._boundDataset = () => this.render();
        this._datasetUnsub = store.subscribe('history.playback.dataset', this._boundDataset);
        this._boundTick = () => this._updateDisplay();
        bus.on('playback-tick', this._boundTick);
    }

    unmount() {
        if (this._datasetUnsub) { this._datasetUnsub(); this._datasetUnsub = null; }
        if (this._boundTick) { bus.off('playback-tick', this._boundTick); this._boundTick = null; }
        this.container = null;
    }

    render() {
        if (!this.container) return;
        const state = store.get('history.playbackState') || 'stopped';
        const speed = store.get('history.playbackSpeed') || 1;
        const time = store.get('history.playbackTime') || 0;
        const duration = this._getDuration();

        this.container.innerHTML = `
            <div class="timeline-control">
                <div class="timeline-control__row" style="display:flex;align-items:center;gap:var(--space-2);">
                    <button class="timeline-control__btn" id="tl-step-back" title="后退">&#9664;&#9664;</button>
                    <button class="timeline-control__btn" id="tl-play-pause" title="${state === 'playing' ? '暂停' : '播放'}">
                        ${state === 'playing' ? '&#9646;&#9646;' : '&#9654;'}
                    </button>
                    <button class="timeline-control__btn" id="tl-step-fwd" title="前进">&#9654;&#9654;</button>
                    <span style="font-size: var(--font-sm); color: var(--color-text-secondary); white-space: nowrap;" id="tl-time">
                        ${this._formatTime(time)} / ${this._formatTime(duration)}
                    </span>
                    <span style="font-size: var(--font-sm); color: var(--color-blue); font-family: var(--font-mono); white-space: nowrap;" id="tl-pct">0%</span>
                    <select class="timeline-control__speed" id="tl-speed">
                        <option value="0.5" ${speed === 0.5 ? 'selected' : ''}>0.5x</option>
                        <option value="1" ${speed === 1 ? 'selected' : ''}>1x</option>
                        <option value="2" ${speed === 2 ? 'selected' : ''}>2x</option>
                        <option value="4" ${speed === 4 ? 'selected' : ''}>4x</option>
                    </select>
                </div>
                <input type="range" class="timeline-control__seek" id="tl-seek" min="0" max="${duration || 1}" value="${time}" step="0.05" style="width:100%;">
                <div style="font-size: var(--font-sm); color: var(--color-text-secondary);" id="tl-task">动作 -- / --</div>
            </div>
        `;

        this._timeEl = this.container.querySelector('#tl-time');
        this._seekEl = this.container.querySelector('#tl-seek');
        this._pctEl = this.container.querySelector('#tl-pct');
        this._taskEl = this.container.querySelector('#tl-task');
        this._playBtnEl = this.container.querySelector('#tl-play-pause');

        // Bind events
        this.container.querySelector('#tl-play-pause')?.addEventListener('click', () => {
            const cur = store.get('history.playbackState') || 'stopped';
            const newState = cur === 'playing' ? 'paused' : 'playing';
            store.set('history.playbackState', newState);
            bus.emit('playback-state-changed', newState);
            this._updateDisplay();
        });

        this.container.querySelector('#tl-step-back')?.addEventListener('click', () => {
            bus.emit('playback-step', -1);
        });

        this.container.querySelector('#tl-step-fwd')?.addEventListener('click', () => {
            bus.emit('playback-step', 1);
        });

        const seek = this._seekEl;
        if (seek) {
            seek.addEventListener('input', () => {
                const t = parseFloat(seek.value);
                store.set('history.playbackTime', t);
                bus.emit('playback-seek', t);
                this._updateDisplay();
            });
        }

        const speedSelect = this.container.querySelector('#tl-speed');
        if (speedSelect) {
            speedSelect.addEventListener('change', () => {
                const spd = parseFloat(speedSelect.value);
                store.set('history.playbackSpeed', spd);
                bus.emit('playback-speed-changed', spd);
            });
        }

        this._updateDisplay();
    }

    /** 播放进度/任务指示增量刷新 (playback-tick 驱动, 避免整 DOM 重建)。 */
    _updateDisplay() {
        const state = store.get('history.playbackState') || 'stopped';
        const time = store.get('history.playbackTime') || 0;
        const duration = this._getDuration();
        const pct = duration > 0 ? Math.min(100, Math.round((time / duration) * 100)) : 0;

        if (this._playBtnEl) {
            const playing = state === 'playing';
            this._playBtnEl.innerHTML = playing ? '&#9646;&#9646;' : '&#9654;';
            this._playBtnEl.title = playing ? '暂停' : '播放';
        }
        if (this._timeEl) this._timeEl.textContent = `${this._formatTime(time)} / ${this._formatTime(duration)}`;
        if (this._pctEl) this._pctEl.textContent = `${pct}%`;
        if (this._seekEl) {
            this._seekEl.value = Math.min(time, duration || 0);
            // range 轨道按进度填充 → 读作进度条
            this._seekEl.style.background = `linear-gradient(to right, var(--color-red) ${pct}%, var(--color-border) ${pct}%)`;
        }
        if (this._taskEl) {
            const info = store.get('history.playback.dataset')?.taskInfo;
            const total = info?.totalActions || 0;
            const cur = total > 0 ? Math.min(total, Math.floor((duration > 0 ? time / duration : 0) * total) + 1) : 0;
            this._taskEl.textContent = `动作 ${cur}/${total} · 状态 ${info?.status || 'idle'}`;
        }
    }

    /** 时长: 优先回放数据集 duration (真实遥测 t 区间), 兜底旧行为。 */
    _getDuration() {
        const ds = store.get('history.playback.dataset');
        if (ds && ds.duration > 0) return ds.duration;
        const trajectory = store.get('trajectory');
        const flown = trajectory?.flown || [];
        if (flown.length > 1) {
            return flown[flown.length - 1].t - flown[0].t || 60;
        }
        return 60;
    }

    _formatTime(seconds) {
        const s = Math.floor(seconds || 0);
        const m = Math.floor(s / 60);
        const sec = s % 60;
        return `${m.toString().padStart(2, '0')}:${sec.toString().padStart(2, '0')}`;
    }
}

export { TimelineControl };
