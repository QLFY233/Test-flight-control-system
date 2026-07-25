/**
 * ConnectionOverlay — Semi-transparent overlay when WebSocket disconnects.
 */

import store from '../state.js';
import { wsManager } from '../shared.js';

class ConnectionOverlay {
    constructor(container) {
        this.container = container;
        this.visible = false;
    }

    show() {
        if (this.visible) return;
        this.visible = true;

        const retryCount = wsManager.getRetryCount();

        this.container.innerHTML = `
            <div class="connection-overlay">
                <div style="font-family:var(--font-mono);font-size:var(--text-3xl);color:var(--color-red);margin-bottom:var(--space-4);">/// SIGNAL LOST</div>
                <div class="connection-overlay__text">
                    连接断开 · 重试 ${retryCount}
                </div>
                <button class="btn btn--secondary" id="btn-retry-connection">
                    [ RECONNECT ]
                </button>
            </div>
        `;

        this.container.style.display = 'flex';

        const retryBtn = this.container.querySelector('#btn-retry-connection');
        if (retryBtn) {
            retryBtn.addEventListener('click', () => {
                wsManager.connect();
            });
        }
    }

    hide() {
        if (!this.visible) return;
        this.visible = false;
        this.container.innerHTML = '';
        this.container.style.display = 'none';
    }
}

export { ConnectionOverlay };
