/**
 * DashboardPage — Data dashboard with multi-panel grid and filter bar.
 * Subscribes to WS dashboard_config for dynamic panel updates.
 */

import store from '../state.js';
import bus from '../event-bus.js';
import { wsManager } from '../shared.js';
import { DashboardGrid } from '../components/DashboardGrid.js';
import { FilterBar } from '../components/FilterBar.js';

class DashboardPage {
    constructor() {
        this.container = null;
        this.title = '数据看板';
        this.grid = null;
        this.filterBar = null;
        this._boundOnDashboardConfig = this._onDashboardConfig.bind(this);
    }

    mount(container) {
        this.container = container;
        this._render();
        this._initGrid();
        this._initFilter();
        wsManager.on('dashboard_config', this._boundOnDashboardConfig);
    }

    unmount() {
        if (this.grid) { this.grid.unmount(); this.grid = null; }
        if (this.filterBar) { this.filterBar.unmount(); this.filterBar = null; }
        wsManager.off('dashboard_config', this._boundOnDashboardConfig);
        this.container = null;
    }

    _render() {
        this.container.innerHTML = `
            <div class="dashboard-page" style="display: flex; flex-direction: column; height: 100%;">
                <div class="dashboard-page__header" style="padding: var(--space-sm) var(--space-md); border-bottom: 1px solid var(--color-border); display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-size: var(--font-lg); font-weight: 600;">数据看板</span>
                    <span style="font-size: var(--font-xs); color: var(--color-text-disabled);">β 工具驱动 · 实时更新</span>
                </div>
                <div id="dashboard-filter-bar"></div>
                <div id="dashboard-grid" style="flex: 1; overflow-y: auto;"></div>
            </div>
        `;
    }

    _initGrid() {
        const gridContainer = this.container?.querySelector('#dashboard-grid');
        if (!gridContainer) return;
        this.grid = new DashboardGrid(gridContainer);
        this.grid.init();
    }

    _initFilter() {
        const filterContainer = this.container?.querySelector('#dashboard-filter-bar');
        if (!filterContainer) return;
        this.filterBar = new FilterBar(filterContainer);
        this.filterBar.mount((filters) => {
            console.log('[Dashboard] filters applied:', filters);
        });
    }

    _onDashboardConfig(payload) {
        if (!payload || !this.grid) return;
        const { panel_id, spec, filter } = payload;
        if (panel_id && spec) {
            this.grid.updatePanel(panel_id, spec);
        }
        if (panel_id && filter && this.filterBar) {
            this.filterBar.applyFilter(filter);
        }
    }
}

export { DashboardPage };
