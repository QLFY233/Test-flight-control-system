/**
 * ConnectionOverlay — Semi-transparent overlay when WebSocket disconnects.
 */

import store from '../store.js';
import { wsManager } from '../app.js';

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
                <div class="connection-overlay__spinner"></div>
                <div class="connection-overlay__text">
                    连接断开，正在重试 (第${retryCount}次)
                </div>
                <button class="btn btn--secondary" id="btn-retry-connection">
                    手动重连
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
