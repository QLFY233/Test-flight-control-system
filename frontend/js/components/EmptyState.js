/**
 * EmptyState — Placeholder component for when there is no content.
 * Usage: new EmptyState({ icon: '...', title: '...', desc: '...', actionText: '...', onAction: () => {} })
 */

class EmptyState {
    /**
     * @param {object} opts
     * @param {string} [opts.icon] - emoji or text icon
     * @param {string} opts.title
     * @param {string} [opts.desc]
     * @param {string} [opts.actionText]
     * @param {Function} [opts.onAction]
     */
    constructor(opts = {}) {
        const { icon = '', title = '', desc = '', actionText = '', onAction = null } = opts;
        this.element = document.createElement('div');
        this.element.className = 'empty-state';
        this.element.innerHTML = `
            ${icon ? `<div class="empty-state__icon">${icon}</div>` : ''}
            <div class="empty-state__title">${title}</div>
            ${desc ? `<div class="empty-state__desc">${desc}</div>` : ''}
            ${actionText ? `<button class="btn btn--secondary empty-state__action-btn">${actionText}</button>` : ''}
        `;

        if (onAction) {
            const btn = this.element.querySelector('.empty-state__action-btn');
            if (btn) {
                btn.addEventListener('click', onAction);
            }
        }
    }

    render() {
        return this.element;
    }

    mount(container) {
        container.innerHTML = '';
        container.appendChild(this.element);
    }
}

export { EmptyState };
