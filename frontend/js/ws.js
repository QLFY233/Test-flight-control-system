/**
 * WebSocket Manager — Persistent connection with auto-reconnect and exponential backoff.
 */

const WS_STATES = {
    CONNECTING: 0,
    OPEN: 1,
    CLOSING: 2,
    CLOSED: 3,
};

class WsManager {
    constructor(url) {
        this.url = url;
        this.ws = null;
        this.handlers = new Map();
        this.reconnectDelay = 1000;
        this.reconnectTimer = null;
        this.maxReconnectDelay = 30000;
        this.intentionalClose = false;
        this.currentRetry = 0;
    }

    /**
     * Open the WebSocket connection.
     */
    connect() {
        if (this.ws && (this.ws.readyState === WS_STATES.OPEN || this.ws.readyState === WS_STATES.CONNECTING)) {
            return;
        }

        this.intentionalClose = false;

        try {
            this.ws = new WebSocket(this.url);
        } catch (e) {
            console.error('[WS] failed to create WebSocket:', e);
            this._scheduleReconnect();
            return;
        }

        this.ws.onopen = () => {
            console.log('[WS] connected');
            this.currentRetry = 0;
            this.reconnectDelay = 1000;
            this._emit('open', null);

            // Notify connection handlers
            this._dispatch({ type: 'connection', payload: { status: 'connected' } });
        };

        this.ws.onmessage = (event) => {
            let data;
            try {
                data = JSON.parse(event.data);
            } catch (e) {
                console.warn('[WS] non-JSON message received:', event.data);
                return;
            }

            if (!data || !data.type) {
                console.warn('[WS] message without type:', data);
                return;
            }

            this._dispatch(data);
        };

        this.ws.onclose = (event) => {
            console.warn(`[WS] closed (code=${event.code}, reason=${event.reason})`);
            this._emit('close', event);

            if (!this.intentionalClose) {
                this._dispatch({ type: 'connection', payload: { status: 'disconnected' } });
                this._scheduleReconnect();
            }
        };

        this.ws.onerror = (event) => {
            console.error('[WS] error:', event);
            this._emit('error', event);
        };
    }

    /**
     * Send a typed JSON message.
     * @param {string} type - message type
     * @param {object} payload - message payload
     */
    send(type, payload = {}) {
        if (!this.ws || this.ws.readyState !== WS_STATES.OPEN) {
            console.warn('[WS] cannot send — not connected');
            return false;
        }

        const msg = JSON.stringify({ type, payload, timestamp: Date.now() });
        try {
            this.ws.send(msg);
            return true;
        } catch (e) {
            console.error('[WS] send error:', e);
            return false;
        }
    }

    /**
     * Register a handler for a message type.
     * @param {string} type - message type to listen for
     * @param {Function} handler - (payload, fullMessage) => void
     */
    on(type, handler) {
        if (!this.handlers.has(type)) {
            this.handlers.set(type, new Set());
        }
        this.handlers.get(type).add(handler);
    }

    /**
     * Remove a handler.
     * @param {string} type
     * @param {Function} handler
     */
    off(type, handler) {
        const set = this.handlers.get(type);
        if (set) {
            set.delete(handler);
        }
    }

    /**
     * Close the connection intentionally (no reconnect).
     */
    disconnect() {
        this.intentionalClose = true;
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
        if (this.ws) {
            this.ws.close(1000, 'Client disconnect');
            this.ws = null;
        }
    }

    /**
     * Get current connection status string.
     */
    getStatus() {
        if (!this.ws) return 'disconnected';
        switch (this.ws.readyState) {
            case WS_STATES.CONNECTING: return 'connecting';
            case WS_STATES.OPEN: return 'connected';
            case WS_STATES.CLOSING: return 'closing';
            case WS_STATES.CLOSED: return 'disconnected';
            default: return 'unknown';
        }
    }

    /**
     * Get current retry count.
     */
    getRetryCount() {
        return this.currentRetry;
    }

    // ---- Internal ----

    _dispatch(data) {
        // Emit to type-specific handlers
        const typeHandlers = this.handlers.get(data.type);
        if (typeHandlers) {
            for (const handler of typeHandlers) {
                try {
                    handler(data.payload, data);
                } catch (e) {
                    console.error(`[WS] handler error for "${data.type}":`, e);
                }
            }
        }

        // Emit to wildcard handlers
        const starHandlers = this.handlers.get('*');
        if (starHandlers) {
            for (const handler of starHandlers) {
                try {
                    handler(data.payload, data);
                } catch (e) {
                    console.error('[WS] wildcard handler error:', e);
                }
            }
        }

        // Emit event
        this._emit('message', data);
    }

    _emit(eventName, data) {
        const handlers = this.handlers.get(`__event:${eventName}`);
        if (handlers) {
            for (const handler of handlers) {
                try {
                    handler(data);
                } catch (e) {
                    console.error(`[WS] event handler error for "${eventName}":`, e);
                }
            }
        }
    }

    _scheduleReconnect() {
        if (this.intentionalClose) return;

        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
        }

        this.currentRetry++;
        console.log(`[WS] reconnecting in ${this.reconnectDelay}ms (attempt ${this.currentRetry})`);

        this._dispatch({ type: 'connection', payload: { status: 'connecting', retryCount: this.currentRetry } });

        this.reconnectTimer = setTimeout(() => {
            this.reconnectTimer = null;
            this.connect();

            // Exponential backoff: 1s, 2s, 4s, 8s, 16s, 30s cap
            this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxReconnectDelay);
        }, this.reconnectDelay);
    }
}

export { WsManager };
