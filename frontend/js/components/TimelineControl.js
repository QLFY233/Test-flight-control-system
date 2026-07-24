/**
 * TimelineControl — History playback controls.
 * Play/pause, seek bar, speed selector.
 */

import store from '../state.js';
import bus from '../event-bus.js';

class TimelineControl {
    constructor(container) {
        this.container = container;
    }

    mount() {
        this.render();
    }

    render() {
        const hist = store.get('history');
        const state = hist.playbackState || 'stopped';
        const speed = hist.playbackSpeed || 1;
        const time = hist.playbackTime || 0;
        const duration = this._getDuration();

        this.container.innerHTML = `
            <div class="timeline-control">
                <button class="timeline-control__btn" id="tl-step-back" title="后退">&#9664;&#9664;</button>
                <button class="timeline-control__btn" id="tl-play-pause" title="${state === 'playing' ? '暂停' : '播放'}">
                    ${state === 'playing' ? '&#9646;&#9646;' : '&#9654;'}
                </button>
                <button class="timeline-control__btn" id="tl-step-fwd" title="前进">&#9654;&#9654;</button>
                <span style="font-size: var(--font-sm); color: var(--color-text-secondary); white-space: nowrap;">
                    ${this._formatTime(time)} / ${this._formatTime(duration)}
                </span>
                <input type="range" class="timeline-control__seek" min="0" max="${duration || 1}" value="${time}" step="0.1" id="tl-seek">
                <select class="timeline-control__speed" id="tl-speed">
                    <option value="0.5" ${speed === 0.5 ? 'selected' : ''}>0.5x</option>
                    <option value="1" ${speed === 1 ? 'selected' : ''}>1x</option>
                    <option value="2" ${speed === 2 ? 'selected' : ''}>2x</option>
                    <option value="4" ${speed === 4 ? 'selected' : ''}>4x</option>
                </select>
            </div>
        `;

        // Bind events
        this.container.querySelector('#tl-play-pause')?.addEventListener('click', () => {
            const newState = state === 'playing' ? 'paused' : 'playing';
            store.set('history.playbackState', newState);
            bus.emit('playback-state-changed', newState);
            this.render();
        });

        this.container.querySelector('#tl-step-back')?.addEventListener('click', () => {
            bus.emit('playback-step', -1);
        });

        this.container.querySelector('#tl-step-fwd')?.addEventListener('click', () => {
            bus.emit('playback-step', 1);
        });

        const seek = this.container.querySelector('#tl-seek');
        if (seek) {
            seek.addEventListener('input', () => {
                const t = parseFloat(seek.value);
                store.set('history.playbackTime', t);
                bus.emit('playback-seek', t);
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
    }

    _getDuration() {
        // Try to get duration from stored session
        const trajectory = store.get('trajectory');
        const flown = trajectory.flown || [];
        if (flown.length > 1) {
            return flown[flown.length - 1].t - flown[0].t || 60;
        }
        return 60; // default 60s
    }

    _formatTime(seconds) {
        const s = Math.floor(seconds);
        const m = Math.floor(s / 60);
        const sec = s % 60;
        return `${m.toString().padStart(2, '0')}:${sec.toString().padStart(2, '0')}`;
    }
}

export { TimelineControl };
