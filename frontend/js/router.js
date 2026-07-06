/**
 * Hash Router — SPA navigation
 * Pages must implement: { mount(container), unmount(), title }
 */

class Router {
    constructor(container) {
        this.container = container;
        this.routes = new Map();
        this.current = null;
        this.currentHash = null;
    }

    /**
     * Register a page controller for a hash.
     * @param {string} hash - e.g. '#/overview'
     * @param {object} controller - { mount, unmount, title }
     */
    register(hash, controller) {
        this.routes.set(hash, controller);
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
     * Handle hash change event.
     */
    _onChange() {
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

        // Find controller
        const controller = this.routes.get(hash);
        if (!controller) {
            console.warn(`[Router] no route registered for "${hash}", falling back to #/overview`);
            if (hash !== '#/overview') {
                this.navigate('#/overview');
                return;
            }
            this.current = null;
            this.currentHash = null;
            return;
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
    }
}

export { Router };
