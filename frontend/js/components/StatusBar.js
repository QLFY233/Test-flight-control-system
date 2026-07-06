/**
 * StatusBar — Top bar showing connection status, drone position, flight mode, segment progress.
 */

import store from '../state.js';

class StatusBar {
    constructor(container) {
        this.container = container;
    }

    mount() {
        const conn = store.get('connection');
        const drone = store.get('drone');
        const flight = store.get('flight');
        const env = store.get('environment');

        const wsStatus = conn.ws || 'disconnected';
        const dotClass = wsStatus === 'connected' ? 'status-bar__dot--connected'
            : wsStatus === 'connecting' ? 'status-bar__dot--connecting'
            : 'status-bar__dot--disconnected';
        const wsLabel = wsStatus === 'connected' ? '已连接'
            : wsStatus === 'connecting' ? '连接中...'
            : '断开';

        const seg = flight.currentSegment || 0;
        const total = flight.totalSegments || 0;
        const segPct = total > 0 ? ((seg / total) * 100) : 0;

        this.container.innerHTML = `
            <div class="status-bar__left">
                <div class="status-bar__indicator">
                    <span class="status-bar__dot ${dotClass}"></span>
                    <span>${wsLabel}</span>
                </div>
                <div class="status-bar__indicator">
                    <span style="color: var(--color-text-disabled);">Drone</span>
                    <span>${drone.connected ? '在线' : '离线'}</span>
                </div>
            </div>
            <div class="status-bar__center">
                <div class="status-bar__indicator">
                    <span>位置:</span>
                    <span>(${drone.position.x.toFixed(1)}, ${drone.position.y.toFixed(1)}, ${drone.position.z.toFixed(1)})</span>
                </div>
                <div class="status-bar__indicator">
                    <span>模式:</span>
                    <span>${flight.mode || '--'}</span>
                </div>
                <div class="status-bar__indicator">
                    <span>段: ${seg}/${total}</span>
                    <div class="status-bar__seg-progress">
                        <div class="status-bar__seg-fill" style="width: ${segPct}%"></div>
                    </div>
                </div>
            </div>
            <div class="status-bar__right">
                <div class="status-bar__indicator">
                    <span>温度: ${env.temperature ?? '--'}°C</span>
                </div>
                <div class="status-bar__indicator">
                    <span>风速: ${env.windSpeed ?? '--'} m/s</span>
                </div>
                <div class="status-bar__indicator">
                    <span>电池: ${drone.battery != null ? drone.battery + '%' : '--'}</span>
                </div>
            </div>
        `;
    }
}

export { StatusBar };
