/**
 * PlaybackEngine — 历史回放引擎 (模块级单例)。
 * 订阅 TimelineControl 总线事件, rAF 按倍速推进 store.history.playbackTime,
 * 计算当前帧索引, 发 playback-tick 驱动进度条/图表游标/3D 等视图。
 *
 * 事件契约 (TimelineControl 已有):
 *   playback-state-changed(state)  playback-seek(t)  playback-step(±1)  playback-speed-changed(speed)
 * 对外事件:
 *   playback-tick({time, index})
 */

import store from '../state.js';
import bus from '../event-bus.js';

// rAF 帧间最大推进 (秒) — tab 切走恢复后 rAF 时间戳可能大跳, 钳制避免瞬移
const MAX_STEP_S = 0.2;

// points 按 t 升序 → 二分查找当前帧索引 (O(log n), 10000 点场景安全)
function _findIndex(points, t) {
    let lo = 0, hi = points.length - 1, ans = 0;
    while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        if (points[mid].t <= t) { ans = mid; lo = mid + 1; }
        else { hi = mid - 1; }
    }
    return ans;
}

class PlaybackEngine {
    constructor() {
        this._rafId = null;
        this._lastTs = null;
        this._mounted = false;
        this._handlers = null;
    }

    /** 挂载: 订阅总线 + 恢复 playing 状态 (页面导航幂等)。 */
    mount() {
        if (this._mounted) return;
        this._mounted = true;
        this._handlers = {
            onState: (s) => {
                store.set('history.playbackState', s);
                if (s === 'playing') this._start();
                else this._stop();
            },
            onSeek: (t) => {
                store.set('history.playbackTime', Math.max(0, t || 0));
                this._emitTick();
            },
            onStep: (dir) => this._step(dir),
            onSpeed: (sp) => store.set('history.playbackSpeed', sp),
        };
        bus.on('playback-state-changed', this._handlers.onState);
        bus.on('playback-seek', this._handlers.onSeek);
        bus.on('playback-step', this._handlers.onStep);
        bus.on('playback-speed-changed', this._handlers.onSpeed);
        if (store.get('history.playbackState') === 'playing') this._start();
    }

    /** 卸载: 停 rAF + 解绑 (切页后回放停止)。 */
    unmount() {
        this._stop();
        if (this._handlers) {
            bus.off('playback-state-changed', this._handlers.onState);
            bus.off('playback-seek', this._handlers.onSeek);
            bus.off('playback-step', this._handlers.onStep);
            bus.off('playback-speed-changed', this._handlers.onSpeed);
            this._handlers = null;
        }
        this._mounted = false;
    }

    _start() {
        if (this._rafId != null) return;
        this._lastTs = null;
        const loop = (now) => {
            this._rafId = requestAnimationFrame(loop);
            if (this._lastTs == null) { this._lastTs = now; return; }
            const dt = Math.min((now - this._lastTs) / 1000, MAX_STEP_S);
            this._lastTs = now;
            this._advance(dt * (store.get('history.playbackSpeed') || 1));
        };
        this._rafId = requestAnimationFrame(loop);
    }

    _stop() {
        if (this._rafId != null) { cancelAnimationFrame(this._rafId); this._rafId = null; }
        this._lastTs = null;
    }

    _advance(dt) {
        const ds = store.get('history.playback.dataset');
        const dur = ds?.duration || 0;
        if (dur <= 0) return;
        let t = store.get('history.playbackTime') || 0;
        t += dt;
        if (t >= dur) {
            store.set('history.playbackTime', dur);
            this._emitTick();
            // 播完自然停止
            store.set('history.playbackState', 'stopped');
            this._stop();
            return;
        }
        store.set('history.playbackTime', t);
        this._emitTick();
    }

    /** 单帧步进 (时间 = 平均帧间隔), 边界钳制。 */
    _step(dir) {
        const ds = store.get('history.playback.dataset');
        const pts = ds?.points || [];
        if (!pts.length) return;
        const frame = pts.length > 1 ? (ds.duration || 0) / pts.length : 1;
        const t = store.get('history.playbackTime') || 0;
        const nt = Math.min(Math.max(0, t + dir * frame), ds.duration || 0);
        store.set('history.playbackTime', nt);
        this._emitTick();
    }

    _emitTick() {
        const ds = store.get('history.playback.dataset');
        const pts = ds?.points || [];
        const t = store.get('history.playbackTime') || 0;
        const index = pts.length ? _findIndex(pts, t) : 0;
        store.set('history.playback.index', index);
        bus.emit('playback-tick', { time: t, index });
    }
}

export const playbackEngine = new PlaybackEngine();
