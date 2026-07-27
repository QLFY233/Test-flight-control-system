/**
 * SessionCard — History session card with date, status badge, summary, and checkbox.
 */

class SessionCard {
    /**
     * @param {object} session
     * @param {string} session.id
     * @param {string} session.date
     * @param {string} session.status - 'success'|'warning'|'error'|'info'
     * @param {string} session.task_summary
     * @param {boolean} [session.selected]
     * @param {object} callbacks
     * @param {Function} callbacks.onClick - (session) => void
     * @param {Function} callbacks.onSelect - (session, checked) => void
     */
    constructor(session, callbacks = {}) {
        this.session = session;
        this.callbacks = callbacks;
    }

    render() {
        const el = document.createElement('div');
        el.className = 'session-card';
        if (this.session.selected) {
            el.classList.add('session-card--selected');
        }

        const statusLabels = {
            success: '成功',
            warning: '警告',
            error: '失败',
            info: '信息',
            completed: '已完成',
            aborted: '已中止',
        };

        const date = this.session.date || this.session.created_at || '';
        let dateStr = '--';
        if (date) {
            try {
                const d = new Date(date);
                if (!isNaN(d.getTime())) {
                    dateStr = d.getFullYear() + '/' +
                        String(d.getMonth() + 1).padStart(2, '0') + '/' +
                        String(d.getDate()).padStart(2, '0') + ' ' +
                        String(d.getHours()).padStart(2, '0') + ':' +
                        String(d.getMinutes()).padStart(2, '0');
                }
            } catch(e) { dateStr = date; }
        }
        const summary = (this.session.task_summary || this.session.description || '无描述').substring(0, 40);

        el.innerHTML = `
            <input type="checkbox" class="session-card__checkbox" ${this.session.selected ? 'checked' : ''}>
            <span class="session-card__badge session-card__badge--${this.session.status || 'info'}">
                ${statusLabels[this.session.status] || this.session.status || '--'}
            </span>
            <span class="session-card__date">${dateStr}</span>
            <span class="session-card__summary" title="${FlightPlanCard_esc(this.session.task_summary || '')}">${FlightPlanCard_esc(summary)}</span>
        `;

        // Click on card (not checkbox)
        el.addEventListener('click', (e) => {
            if (e.target.tagName === 'INPUT') return;
            this.callbacks.onClick && this.callbacks.onClick(this.session);
        });

        const checkbox = el.querySelector('.session-card__checkbox');
        if (checkbox) {
            checkbox.addEventListener('change', () => {
                this.callbacks.onSelect && this.callbacks.onSelect(this.session, checkbox.checked);
            });
        }

        return el;
    }
}

function FlightPlanCard_esc(text) {
    const div = document.createElement('div');
    div.textContent = String(text || '');
    return div.innerHTML;
}

export { SessionCard };
