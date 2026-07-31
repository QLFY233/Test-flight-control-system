/**
 * FlightPlanCard — Structured card showing a flight plan with ActionCommand actions.
 * schema_version=2: uses actions format (not legacy segments/waypoints).
 */

class FlightPlanCard {
    /**
     * @param {object} plan
     * @param {Array} plan.actions - array of ActionCommand entries [{code, value?, target?, comment?}, ...]
     * @param {object} callbacks
     * @param {Function} callbacks.onApprove
     * @param {Function} callbacks.onReject
     * @param {Function} callbacks.onOverlay3D
     */
    constructor(plan, callbacks = {}) {
        this.plan = plan;
        this.callbacks = callbacks;
        this.element = null;
    }

    render() {
        const container = document.createElement('div');
        container.className = 'flight-plan-card';

        const title = this.plan.title || this.plan.name || '飞行计划';
        const actions = this.plan.actions || [];
        const intent = this.plan.intent || this.plan.summary || '';
        const hasActions = actions.length > 0;

        const bodyHtml = hasActions
            ? this._renderActions(actions)
            : `<div style="padding: var(--space-md);">
                <div style="color: var(--color-text-secondary); margin-bottom: var(--space-sm);">意图描述:</div>
                <div style="white-space: pre-wrap;">${FlightPlanCard._esc(intent)}</div>
               </div>`;

        container.innerHTML = `
            <div class="flight-plan-card__header">
                <span class="flight-plan-card__title">${FlightPlanCard._esc(title)}</span>
                ${hasActions ? '<span class="flight-plan-card__badge" style="font-size: var(--font-xs); color: var(--color-cyan); border: 1px solid var(--color-cyan); border-radius: var(--radius-sm); padding: 0 6px;">动作序列</span>' : ''}
                <span style="font-size: var(--font-xs); color: var(--color-text-disabled); margin-left: auto;">
                    ${this.plan.summary ? FlightPlanCard._esc(this.plan.summary) : ''}
                </span>
            </div>
            <div class="flight-plan-card__body">
                ${bodyHtml}
            </div>
            <div class="flight-plan-card__actions">
                <button class="btn btn--primary btn--sm approve-btn">✓ 批准</button>
                <button class="btn btn--danger btn--sm reject-btn">✗ 驳回</button>
                <button class="btn btn--ghost btn--sm overlay-btn" title="预览(未批准)">叠加到3D</button>
            </div>
        `;

        // Bind events
        const approveBtn = container.querySelector('.approve-btn');
        const rejectBtn = container.querySelector('.reject-btn');
        const overlayBtn = container.querySelector('.overlay-btn');

        if (approveBtn) approveBtn.addEventListener('click', () => this.callbacks.onApprove && this.callbacks.onApprove(this.plan));
        if (rejectBtn) rejectBtn.addEventListener('click', () => this.callbacks.onReject && this.callbacks.onReject(this.plan));
        if (overlayBtn) overlayBtn.addEventListener('click', () => this.callbacks.onOverlay3D && this.callbacks.onOverlay3D(this.plan));

        this.element = container;
        return container;
    }

    /**
     * Render ActionCommand entries (schema_version=2 format).
     */
    _renderActions(actions) {
        return actions.map((a, i) => {
            const code = a.code || 'UNKNOWN';
            const value = a.value != null ? a.value : '';
            const target = a.target || {};
            const comment = a.comment || a.description || '';
            const units = a.units || '';

            return `
                <div class="flight-plan-card__segment">
                    <div class="flight-plan-card__segment-header">
                        <span class="flight-plan-card__segment-id">${i + 1}</span>
                        <span class="flight-plan-card__segment-name" style="font-family: var(--font-mono);">${FlightPlanCard._esc(code)}</span>
                        ${comment ? `<span style="font-size: var(--font-xs); color: var(--color-text-disabled);">${FlightPlanCard._esc(comment)}</span>` : ''}
                    </div>
                    <div class="flight-plan-card__waypoint">
                        <span>&#9679;</span>
                        <span style="font-family: var(--font-mono);">
                            ${code === 'goto' || code === 'move'
                                ? `目标: (${target[0] != null ? Number(target[0]).toFixed(2) : '?'}, ${target[1] != null ? Number(target[1]).toFixed(2) : '?'}, ${target[2] != null ? Number(target[2]).toFixed(2) : '?'})`
                                : value ? `${units ? value + ' ' + units : value}` : ''
                            }
                        </span>
                    </div>
                </div>
            `;
        }).join('');
    }

    /**
     * Mount/re-render the card into a container.
     */
    mount(container) {
        container.innerHTML = '';
        container.appendChild(this.render());
    }

    static _esc(text) {
        const div = document.createElement('div');
        div.textContent = String(text);
        return div.innerHTML;
    }
}

export { FlightPlanCard };
