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
        // 空态兜底: WS 断连 / 无遥测时显示引导横幅
        this._statusUnsubs = [
            store.subscribe('connection', () => this._updateStatusBanner()),
            store.subscribe('drone', () => this._updateStatusBanner()),
        ];
        this._updateStatusBanner();
    }

    unmount() {
        if (this.grid) { this.grid.unmount(); this.grid = null; }
        if (this.filterBar) { this.filterBar.unmount(); this.filterBar = null; }
        wsManager.off('dashboard_config', this._boundOnDashboardConfig);
        if (this._statusUnsubs) { this._statusUnsubs.forEach(u => u()); this._statusUnsubs = []; }
        this.container = null;
    }

    _render() {
        // Reset container to full-width (previous page may have set row flex)
        this.container.style.cssText = 'width:100%;border-right:none;display:flex;flex-direction:column;flex:1;overflow:hidden';
        this.container.innerHTML = `
            <div class="dashboard-page" style="display: flex; flex-direction: column; height: 100%;">
                <div class="dashboard-page__header" style="padding: var(--space-3) var(--space-4); border-bottom: var(--border-thin); display: flex; justify-content: space-between; align-items: center; background: var(--color-surface);">
                    <span style="font-family:var(--font-mono);font-size:var(--text-xs);letter-spacing:var(--track-widest);text-transform:uppercase;color:var(--color-text-disabled);">[ DASHBOARD ]</span>
                    <span style="font-family:var(--font-mono);font-size:var(--text-2xs);letter-spacing:var(--track-wider);text-transform:uppercase;color:var(--color-text-disabled);">BETA TOOL DRIVEN · REALTIME</span>
                </div>
                <div id="dashboard-status" style="display:none;padding:var(--space-2) var(--space-4);font-family:var(--font-mono);font-size:var(--text-2xs);letter-spacing:var(--track-wide);color:var(--color-amber);background:rgba(255,179,0,0.06);border-bottom:var(--border-hair);align-items:center;"></div>
                <div id="dashboard-filter-bar"></div>
                <div id="dashboard-grid" style="flex: 1; overflow-y: auto; padding: var(--space-3);"></div>
            </div>
        `;
    }

    /**
     * 空态兜底: WS 未连接 / 尚未收到遥测时显示引导横幅, 数据到达后隐藏。
     */
    _updateStatusBanner() {
        const el = this.container?.querySelector('#dashboard-status');
        if (!el) return;
        const wsConnected = store.get('connection.ws') === 'connected';
        const hasPose = store.get('drone.timestamp') != null;
        let msg = null;
        if (!wsConnected) {
            msg = '// 连接断开，等待实时数据…';
        } else if (!hasPose) {
            msg = '// 无实时数据 — 启动飞行后自动填充 · 或到 [ 历史 ] 页查看过往记录';
        }
        el.style.display = msg ? 'flex' : 'none';
        el.textContent = msg || '';
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
