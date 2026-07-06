/**
 * FlightPlanCard — Structured card showing a flight plan with segments, waypoints, and action buttons.
 */

class FlightPlanCard {
    /**
     * @param {object} plan
     * @param {Array} plan.segments - array of segment objects
     * @param {object} callbacks
     * @param {Function} callbacks.onApprove
     * @param {Function} callbacks.onModify - (plan) => void
     * @param {Function} callbacks.onReject
     * @param {Function} callbacks.onOverlay3D
     */
    constructor(plan, callbacks = {}) {
        this.plan = plan;
        this.callbacks = callbacks;
        this.element = null;
        this.modifyMode = false;
        this.modifiedSegments = null;
    }

    render() {
        const container = document.createElement('div');
        container.className = 'flight-plan-card';

        const title = this.plan.title || this.plan.name || '飞行计划';

        if (this.modifyMode) {
            container.innerHTML = this._renderModifyMode();
        } else {
            let segmentsHtml = '';
            if (this.plan.segments && this.plan.segments.length > 0) {
                segmentsHtml = this.plan.segments.map((seg, i) => `
                    <div class="flight-plan-card__segment">
                        <div class="flight-plan-card__segment-header">
                            <span class="flight-plan-card__segment-id">${i + 1}</span>
                            <span class="flight-plan-card__segment-name">${seg.name || `段 ${i + 1}`}</span>
                            <span style="font-size: var(--font-xs); color: var(--color-text-disabled);">
                                ${seg.type || ''}
                            </span>
                        </div>
                        ${(seg.waypoints || []).map((wp, j) => `
                            <div class="flight-plan-card__waypoint">
                                <span>&#9679;</span>
                                <span>航点${j + 1}: (${wp.x != null ? wp.x.toFixed(1) : '?'}, ${wp.y != null ? wp.y.toFixed(1) : '?'}, ${wp.z != null ? wp.z.toFixed(1) : '?'})</span>
                                ${wp.label ? `<span style="color: var(--color-text-disabled);">${wp.label}</span>` : ''}
                            </div>
                        `).join('')}
                        ${seg.constraints ? `
                            <div class="flight-plan-card__waypoint">
                                <span style="color: var(--color-warning);">&#9888;</span>
                                <span style="color: var(--color-text-secondary);">约束: ${Array.isArray(seg.constraints) ? seg.constraints.join(', ') : seg.constraints}</span>
                            </div>
                        ` : ''}
                    </div>
                `).join('');
            } else {
                segmentsHtml = '<div style="padding: var(--space-md); color: var(--color-text-disabled);">无航段数据</div>';
            }

            container.innerHTML = `
                <div class="flight-plan-card__header">
                    <span class="flight-plan-card__title">${FlightPlanCard._esc(title)}</span>
                    <span style="font-size: var(--font-xs); color: var(--color-text-disabled);">
                        ${this.plan.total_distance ? `总距: ${this.plan.total_distance}m` : ''}
                    </span>
                </div>
                <div class="flight-plan-card__body">
                    ${segmentsHtml}
                </div>
                <div class="flight-plan-card__actions">
                    <button class="btn btn--primary btn--sm approve-btn">✓ 批准</button>
                    <button class="btn btn--secondary btn--sm modify-btn">✎ 修改</button>
                    <button class="btn btn--danger btn--sm reject-btn">✗ 驳回</button>
                    <button class="btn btn--ghost btn--sm overlay-btn">叠加到3D</button>
                </div>
            `;

            // Bind events
            const approveBtn = container.querySelector('.approve-btn');
            const modifyBtn = container.querySelector('.modify-btn');
            const rejectBtn = container.querySelector('.reject-btn');
            const overlayBtn = container.querySelector('.overlay-btn');

            if (approveBtn) approveBtn.addEventListener('click', () => this.callbacks.onApprove && this.callbacks.onApprove(this.plan));
            if (rejectBtn) rejectBtn.addEventListener('click', () => this.callbacks.onReject && this.callbacks.onReject(this.plan));
            if (overlayBtn) overlayBtn.addEventListener('click', () => this.callbacks.onOverlay3D && this.callbacks.onOverlay3D(this.plan));
            if (modifyBtn) {
                modifyBtn.addEventListener('click', () => {
                    this.modifyMode = true;
                    this.modifiedSegments = JSON.parse(JSON.stringify(this.plan.segments || []));
                    this.render();
                });
            }
        }

        this.element = container;
        return container;
    }

    _renderModifyMode() {
        let segmentsHtml = (this.modifiedSegments || []).map((seg, i) => {
            let wpsHtml = (seg.waypoints || []).map((wp, j) => `
                <div class="flight-plan-card__waypoint">
                    <span>&#9679;</span>
                    <span>WP${j + 1}:</span>
                    <input class="flight-plan-card__edit-input" data-seg="${i}" data-wp="${j}" data-field="x" value="${wp.x != null ? wp.x : ''}" placeholder="x">
                    <input class="flight-plan-card__edit-input" data-seg="${i}" data-wp="${j}" data-field="y" value="${wp.y != null ? wp.y : ''}" placeholder="y">
                    <input class="flight-plan-card__edit-input" data-seg="${i}" data-wp="${j}" data-field="z" value="${wp.z != null ? wp.z : ''}" placeholder="z">
                </div>
            `).join('');

            return `
                <div class="flight-plan-card__segment">
                    <div class="flight-plan-card__segment-header">
                        <span class="flight-plan-card__segment-id">${i + 1}</span>
                        <input class="flight-plan-card__edit-input" data-seg="${i}" data-field="name" value="${seg.name || ''}" placeholder="段名" style="width: 80px;">
                    </div>
                    ${wpsHtml}
                </div>
            `;
        }).join('');

        return `
            <div class="flight-plan-card__header">
                <span class="flight-plan-card__title">编辑模式</span>
            </div>
            <div class="flight-plan-card__body">${segmentsHtml}</div>
            <div class="flight-plan-card__actions">
                <button class="btn btn--primary btn--sm save-btn">✓ 保存修改</button>
                <button class="btn btn--ghost btn--sm cancel-btn">取消</button>
            </div>
        `;
    }

    /**
     * Re-render the card (called after modify mode toggle).
     */
    mount(container) {
        container.innerHTML = '';
        container.appendChild(this.render());

        // If in modify mode, bind edit inputs and buttons
        if (this.modifyMode) {
            const saveBtn = container.querySelector('.save-btn');
            const cancelBtn = container.querySelector('.cancel-btn');

            if (saveBtn) {
                saveBtn.addEventListener('click', () => {
                    // Read all inputs back into modifiedSegments
                    container.querySelectorAll('.flight-plan-card__edit-input').forEach((input) => {
                        const segIdx = parseInt(input.dataset.seg);
                        const wpIdx = input.dataset.wp;
                        const field = input.dataset.field;

                        if (wpIdx !== undefined) {
                            // Waypoint field
                            if (!this.modifiedSegments[segIdx].waypoints[wpIdx]) return;
                            const val = parseFloat(input.value);
                            this.modifiedSegments[segIdx].waypoints[wpIdx][field] = isNaN(val) ? null : val;
                        } else {
                            // Segment field
                            this.modifiedSegments[segIdx][field] = input.value;
                        }
                    });

                    const modifiedPlan = { ...this.plan, segments: this.modifiedSegments };
                    this.modifyMode = false;
                    this.plan = modifiedPlan;
                    this.callbacks.onModify && this.callbacks.onModify(modifiedPlan);
                    this.mount(container);
                });
            }

            if (cancelBtn) {
                cancelBtn.addEventListener('click', () => {
                    this.modifyMode = false;
                    this.mount(container);
                });
            }
        }
    }

    static _esc(text) {
        const div = document.createElement('div');
        div.textContent = String(text);
        return div.innerHTML;
    }
}

export { FlightPlanCard };
