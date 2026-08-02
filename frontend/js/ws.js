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
        // 心跳探测：interval 内若已收到过数据但长时间静默，判定连接假活并主动断开重连
        this.heartbeatInterval = 25000;
        this.heartbeatMissLimit = 3;
        this.lastMessageTs = Date.now();
        this._everReceived = false;
        this.pingTimer = null;
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
            this._everReceived = false;
            this.lastMessageTs = Date.now();
            this._startHeartbeat();
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

            this._everReceived = true;
            this.lastMessageTs = Date.now();
            this._dispatch(data);
        };

        this.ws.onclose = (event) => {
            console.warn(`[WS] closed (code=${event.code}, reason=${event.reason})`);
            this._stopHeartbeat();
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
        this._stopHeartbeat();
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
        // 兼容两种载荷结构：内部构造的消息带 payload 键（{type, payload}），
        // 后端广播为顶层字段（{type, ...}，无 payload 键）。统一取 payload ?? data。
        const payload = data.payload !== undefined ? data.payload : data;

        // Emit to type-specific handlers
        const typeHandlers = this.handlers.get(data.type);
        if (typeHandlers) {
            for (const handler of typeHandlers) {
                try {
                    handler(payload, data);
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
                    handler(payload, data);
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

        // 指数退避加 ±20% 随机抖动，避免多客户端同步重连冲击服务端
        const jitter = 0.8 + Math.random() * 0.4;
        const delay = Math.round(this.reconnectDelay * jitter);
        console.log(`[WS] reconnecting in ${delay}ms (attempt ${this.currentRetry})`);

        this._dispatch({ type: 'connection', payload: { status: 'connecting', retryCount: this.currentRetry } });

        this.reconnectTimer = setTimeout(() => {
            this.reconnectTimer = null;
            this.connect();

            // Exponential backoff: 1s, 2s, 4s, 8s, 16s, 30s cap
            this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxReconnectDelay);
        }, delay);
    }

    /**
     * 心跳探测：周期性发送应用层 ping（保持代理/NAT 连接活跃），
     * 并在「曾收到过数据但长时间静默」时判定假活连接并主动断开以触发重连。
     */
    _startHeartbeat() {
        this._stopHeartbeat();
        this.pingTimer = setInterval(() => {
            if (!this.ws || this.ws.readyState !== WS_STATES.OPEN) return;

            try {
                this.ws.send(JSON.stringify({ type: 'ping', timestamp: Date.now() }));
            } catch (e) {
                console.warn('[WS] heartbeat send failed:', e);
                this.ws.close(4000, 'heartbeat send failed');
                return;
            }

            const idleMs = Date.now() - this.lastMessageTs;
            if (this._everReceived && idleMs > this.heartbeatInterval * this.heartbeatMissLimit) {
                console.warn(`[WS] heartbeat timeout (idle ${idleMs}ms) — closing stale connection`);
                this.ws.close(4000, 'heartbeat timeout');
            }
        }, this.heartbeatInterval);
    }

    _stopHeartbeat() {
        if (this.pingTimer) {
            clearInterval(this.pingTimer);
            this.pingTimer = null;
        }
    }
}

export { WsManager };
