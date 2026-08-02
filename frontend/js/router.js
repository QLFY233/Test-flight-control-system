/**
 * Hash Router — SPA navigation
 * Pages must implement: { mount(container), unmount(), title }
 * Supports lazy-loading via async factory functions.
 */

class Router {
    constructor(container) {
        this.container = container;
        this.routes = new Map();      // hash -> { controller | factory }
        this.pageCache = new Map();   // hash -> resolved controller instance
        this.current = null;
        this.currentHash = null;
        this._changing = false;
    }

    /**
     * Register a page controller or lazy factory for a hash.
     * @param {string} hash - e.g. '#/overview'
     * @param {object|Function} controllerOrFactory - page instance or async () => page instance
     */
    register(hash, controllerOrFactory) {
        this.routes.set(hash, controllerOrFactory);
    }

    /**
     * Navigate to a hash.
     * @param {string} hash - e.g. '#/overview'
     */
    navigate(hash) {
        window.location.hash = hash;
    }

    /**
     * Start listening for hash changes and load initial page.
     */
    init() {
        window.addEventListener('hashchange', () => this._onChange());
        this._onChange();
    }

    /**
     * Handle hash change event (async to support lazy-loaded pages).
     * 竞态处理：动态 import() 期间再次发生 hashchange 时，旧的 _onChange 在
     * finally 中对比当前 hash，若已被新一轮导航改变则递归补跑，避免导航被吞。
     */
    async _onChange() {
        if (this._changing) return;
        this._changing = true;

        try {
            const hash = window.location.hash || '#/overview';
            if (hash === this.currentHash) return; // same page

            // Unmount current
            if (this.current && this.current.unmount) {
                try {
                    this.current.unmount();
                } catch (e) {
                    console.error('[Router] unmount error:', e);
                }
            }

            // Find route entry
            const entry = this.routes.get(hash);
            if (!entry) {
                console.warn(`[Router] no route registered for "${hash}", falling back to #/overview`);
                if (hash !== '#/overview') {
                    this._changing = false;
                    this.navigate('#/overview');
                    return;
                }
                this.current = null;
                this.currentHash = null;
                this._changing = false;
                return;
            }

            // Resolve controller (support lazy factory)
            let controller = this.pageCache.get(hash) || null;
            if (!controller) {
                if (typeof entry === 'function') {
                    // Lazy factory: call it to get the page instance
                    try {
                        controller = await entry();
                    } catch (e) {
                        console.error(`[Router] failed to load page for "${hash}":`, e);
                        // Show error in container
                        this.container.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--color-error);">页面加载失败: ${hash}</div>`;
                        this._changing = false;
                        return;
                    }
                    this.pageCache.set(hash, controller);
                } else {
                    controller = entry;
                }
            }

            // Mount new
            this.currentHash = hash;
            this.current = controller;
            if (controller.mount) {
                try {
                    controller.mount(this.container);
                } catch (e) {
                    console.error('[Router] mount error:', e);
                }
            }

            // Update document title
            if (controller.title) {
                document.title = `${controller.title} - 试飞控制系统`;
            }
        } finally {
            this._changing = false;
            // 若本次导航期间 hash 又变了（快速连点），补跑一次以收敛到最终目标页
            const finalHash = window.location.hash || '#/overview';
            if (finalHash !== this.currentHash && !this._changing) {
                this._onChange();
            }
        }
    }
}

export { Router };
