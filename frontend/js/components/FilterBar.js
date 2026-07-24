/**
 * FilterBar — Data filter controls driven by WS dashboard_set_filter or manual input.
 * Provides time range, data type, and threshold filters.
 */

class FilterBar {
    constructor(container) {
        this.container = container;
        this.filters = {
            timeRange: 'last_60s',
            dataType: 'all',
            threshold: null,
        };
        this._onChange = null;
    }

    /**
     * @param {Function} onChange - (filters) => void
     */
    mount(onChange) {
        this._onChange = onChange;
        this._render();
    }

    unmount() {
        this.container = null;
        this._onChange = null;
    }

    /**
     * Apply filters from external source (WS dashboard_set_filter).
     * @param {object} filter - partial filter object
     */
    applyFilter(filter) {
        if (filter.time) this.filters.timeRange = filter.time;
        if (filter.type) this.filters.dataType = filter.type;
        if (filter.threshold != null) this.filters.threshold = filter.threshold;
        this._render();
        if (this._onChange) this._onChange({ ...this.filters });
    }

    getFilters() {
        return { ...this.filters };
    }

    _render() {
        if (!this.container) return;

        this.container.innerHTML = `
            <div class="filter-bar" style="display: flex; gap: var(--space-sm); padding: var(--space-sm) var(--space-md); align-items: center; flex-wrap: wrap; border-bottom: 1px solid var(--color-border);">
                <span style="font-size: var(--font-xs); color: var(--color-text-secondary);">筛选:</span>

                <select class="input input--sm" id="filter-time" style="width: 110px;">
                    <option value="last_30s" ${this.filters.timeRange === 'last_30s' ? 'selected' : ''}>最近 30s</option>
                    <option value="last_60s" ${this.filters.timeRange === 'last_60s' ? 'selected' : ''}>最近 60s</option>
                    <option value="last_5m" ${this.filters.timeRange === 'last_5m' ? 'selected' : ''}>最近 5min</option>
                    <option value="last_30m" ${this.filters.timeRange === 'last_30m' ? 'selected' : ''}>最近 30min</option>
                    <option value="all" ${this.filters.timeRange === 'all' ? 'selected' : ''}>全部</option>
                </select>

                <select class="input input--sm" id="filter-type" style="width: 100px;">
                    <option value="all" ${this.filters.dataType === 'all' ? 'selected' : ''}>全部类型</option>
                    <option value="telemetry" ${this.filters.dataType === 'telemetry' ? 'selected' : ''}>遥测</option>
                    <option value="alert" ${this.filters.dataType === 'alert' ? 'selected' : ''}>告警</option>
                    <option value="action" ${this.filters.dataType === 'action' ? 'selected' : ''}>动作</option>
                </select>

                <input type="number" class="input input--sm" id="filter-threshold" placeholder="阈值" value="${this.filters.threshold ?? ''}" style="width: 70px;" title="阈值过滤">

                <button class="btn btn--ghost btn--sm" id="btn-filter-reset">重置</button>

                <span style="font-size: 10px; color: var(--color-text-disabled); margin-left: auto;" id="filter-summary"></span>
            </div>
        `;

        this._bindEvents();
    }

    _bindEvents() {
        const timeSelect = this.container?.querySelector('#filter-time');
        const typeSelect = this.container?.querySelector('#filter-type');
        const thresholdInput = this.container?.querySelector('#filter-threshold');
        const resetBtn = this.container?.querySelector('#btn-filter-reset');

        const emitChange = () => {
            this.filters.timeRange = timeSelect?.value || 'last_60s';
            this.filters.dataType = typeSelect?.value || 'all';
            this.filters.threshold = thresholdInput?.value ? parseFloat(thresholdInput.value) : null;
            if (this._onChange) this._onChange({ ...this.filters });
        };

        timeSelect?.addEventListener('change', emitChange);
        typeSelect?.addEventListener('change', emitChange);
        thresholdInput?.addEventListener('change', emitChange);
        resetBtn?.addEventListener('click', () => {
            this.filters = { timeRange: 'last_60s', dataType: 'all', threshold: null };
            this._render();
            if (this._onChange) this._onChange({ ...this.filters });
        });
    }
}

export { FilterBar };
