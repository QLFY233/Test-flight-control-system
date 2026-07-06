/**
 * Global Event Bus — Decoupled pub/sub for application-wide events.
 * Complements the Store (which is for state) with transient events.
 */

class EventBus {
    constructor() {
        this._handlers = new Map(); // event -> Set<handler>
    }

    /**
     * Register an event handler.
     * @param {string} event
     * @param {Function} handler - (...args) => void
     */
    on(event, handler) {
        if (!this._handlers.has(event)) {
            this._handlers.set(event, new Set());
        }
        this._handlers.get(event).add(handler);
    }

    /**
     * Remove an event handler.
     * @param {string} event
     * @param {Function} handler
     */
    off(event, handler) {
        const set = this._handlers.get(event);
        if (set) {
            set.delete(handler);
        }
    }

    /**
     * Emit an event with arguments.
     * @param {string} event
     * @param {...any} args
     */
    emit(event, ...args) {
        const set = this._handlers.get(event);
        if (set) {
            for (const handler of set) {
                try {
                    handler(...args);
                } catch (e) {
                    console.error(`[EventBus] handler error for "${event}":`, e);
                }
            }
        }
    }

    /**
     * Register a one-time handler.
     * @param {string} event
     * @param {Function} handler
     */
    once(event, handler) {
        const wrapper = (...args) => {
            this.off(event, wrapper);
            handler(...args);
        };
        this.on(event, wrapper);
    }
}

const bus = new EventBus();
export default bus;
