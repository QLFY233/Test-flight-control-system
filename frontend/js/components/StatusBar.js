/**
 * StatusBar — Top bar showing connection status, drone position, flight mode, action progress.
 */

import store from '../state.js';
import { esc } from '../escape.js';

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

        const seg = flight.currentAction || 0;
        const total = flight.totalActions || 0;
        const segPct = total > 0 ? ((seg / total) * 100) : 0;

        this.container.innerHTML = `
            <div class="status-bar__left">
                <div class="status-bar__indicator">
                    <span class="status-bar__dot ${dotClass}"></span>
                    <span>[ ${wsLabel.toUpperCase()} ]</span>
                </div>
                <span class="status-bar__sep"></span>
                <div class="status-bar__indicator">
                    <span style="color:var(--color-text-disabled)">DRONE</span>
                    <span>${drone.connected ? 'ONLINE' : 'OFFLINE'}</span>
                </div>
            </div>
            <div class="status-bar__center">
                <div class="status-bar__indicator">
                    <span style="color:var(--color-text-disabled)">POS</span>
                    <span>(${drone.position.x.toFixed(1)}, ${drone.position.y.toFixed(1)}, ${drone.position.z.toFixed(1)})</span>
                </div>
                <span class="status-bar__sep"></span>
                <div class="status-bar__indicator">
                    <span style="color:var(--color-text-disabled)">MODE</span>
                    <span>${esc(flight.mode || '--')}</span>
                </div>
                <span class="status-bar__sep"></span>
                <div class="status-bar__indicator">
                    <span style="color:var(--color-text-disabled)">SEQ</span>
                    <span>${seg}/${total}</span>
                </div>
            </div>
            <div class="status-bar__right">
                <div class="status-bar__indicator">
                    <span style="color:var(--color-text-disabled)">TEMP</span>
                    <span>${env.temperature ?? '--'}°C</span>
                </div>
                <span class="status-bar__sep"></span>
                <div class="status-bar__indicator">
                    <span style="color:var(--color-text-disabled)">WIND</span>
                    <span>${env.windSpeed ?? '--'} m/s</span>
                </div>
                <span class="status-bar__sep"></span>
                <div class="status-bar__indicator">
                    <span style="color:var(--color-text-disabled)">BATT</span>
                    <span>${drone.battery != null ? drone.battery + '%' : '--'}</span>
                </div>
            </div>
        `;
    }
}

export { StatusBar };
