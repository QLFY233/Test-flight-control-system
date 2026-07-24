/**
 * DashboardGrid — Multi-panel grid container with drag-to-reorder.
 * Manages panel_id ↔ DashboardPanel mapping.
 */

import { DashboardPanel } from './DashboardPanel.js';

class DashboardGrid {
    constructor(container) {
        this.container = container;
        this.panels = new Map(); // panelId -> DashboardPanel
        this.panelOrder = []; // ordered panelId array
        this.dragSourceIndex = -1;
    }

    /**
     * Initialize grid with a set of panel specs.
     * @param {Array<{id: string, spec: object}>} panelDefs
     */
    init(panelDefs = []) {
        if (!this.container) return;

        const defs = panelDefs.length > 0 ? panelDefs : this._defaultPanels();
        this.panelOrder = defs.map(d => d.id);

        this._render();

        defs.forEach(def => {
            const panel = new DashboardPanel(def.id, def.spec);
            this.panels.set(def.id, panel);
        });

        this._mountPanels();
    }

    /**
     * Add or update a panel from WS dashboard_config.
     * @param {string} panelId
     * @param {object} spec
     */
    updatePanel(panelId, spec) {
        if (this.panels.has(panelId)) {
            const panel = this.panels.get(panelId);
            panel.updateSpec(spec);
        } else {
            // New panel
            if (!this.panelOrder.includes(panelId)) {
                this.panelOrder.push(panelId);
            }
            const panel = new DashboardPanel(panelId, spec);
            this.panels.set(panelId, panel);
            this._render();
            this._mountPanels();
        }
    }

    /**
     * Remove a panel.
     */
    removePanel(panelId) {
        const panel = this.panels.get(panelId);
        if (panel) {
            panel.unmount();
            this.panels.delete(panelId);
        }
        this.panelOrder = this.panelOrder.filter(id => id !== panelId);
        this._render();
        this._mountPanels();
    }

    unmount() {
        this.panels.forEach(p => p.unmount());
        this.panels.clear();
        this.panelOrder = [];
        this.container = null;
    }

    _render() {
        this.container.innerHTML = `
            <div class="dashboard-grid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: var(--space-sm); padding: var(--space-sm); height: 100%;">
                ${this.panelOrder.map((id, i) => `
                    <div class="dashboard-grid__cell" data-panel-id="${id}" draggable="true" style="border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface-raised); min-height: 180px; display: flex; flex-direction: column; position: relative;">
                        <div class="dashboard-grid__drag-handle" style="cursor: grab; padding: 2px 6px; text-align: center; color: var(--color-text-disabled); font-size: 10px; border-bottom: 1px solid var(--color-border);" title="拖拽排序">⠿</div>
                        <div class="dashboard-grid__panel-content" style="flex: 1; min-height: 0;" id="dash-panel-${id}"></div>
                        <button class="dashboard-grid__close-btn" data-panel-id="${id}" style="position: absolute; top: 2px; right: 4px; background: none; border: none; color: var(--color-text-disabled); cursor: pointer; font-size: 12px; padding: 2px;">✕</button>
                    </div>
                `).join('')}
                <div class="dashboard-grid__add-cell" style="border: 1px dashed var(--color-border); border-radius: var(--radius-md); min-height: 180px; display: flex; align-items: center; justify-content: center; cursor: pointer; color: var(--color-text-disabled);">
                    + 添加面板
                </div>
            </div>
        `;

        this._bindDragEvents();
        this._bindCloseEvents();
    }

    _mountPanels() {
        this.panels.forEach((panel, id) => {
            const contentEl = this.container?.querySelector(`#dash-panel-${id}`);
            if (contentEl && contentEl.children.length === 0) {
                panel.mount(contentEl);
            }
        });
    }

    _bindDragEvents() {
        const cells = this.container?.querySelectorAll('.dashboard-grid__cell');
        cells?.forEach((cell, i) => {
            cell.addEventListener('dragstart', (e) => {
                this.dragSourceIndex = i;
                e.dataTransfer.effectAllowed = 'move';
                cell.style.opacity = '0.4';
            });
            cell.addEventListener('dragend', () => {
                cell.style.opacity = '1';
                this.dragSourceIndex = -1;
            });
            cell.addEventListener('dragover', (e) => {
                e.preventDefault();
                cell.style.borderColor = 'var(--color-cyan)';
            });
            cell.addEventListener('dragleave', () => {
                cell.style.borderColor = '';
            });
            cell.addEventListener('drop', (e) => {
                e.preventDefault();
                cell.style.borderColor = '';
                const fromIdx = this.dragSourceIndex;
                const toIdx = i;
                if (fromIdx >= 0 && fromIdx !== toIdx) {
                    const [moved] = this.panelOrder.splice(fromIdx, 1);
                    this.panelOrder.splice(toIdx, 0, moved);
                    this._render();
                    this._mountPanels();
                }
            });
        });

        // Add panel button
        const addCell = this.container?.querySelector('.dashboard-grid__add-cell');
        if (addCell) {
            addCell.addEventListener('click', () => {
                const newId = 'panel-' + Date.now();
                this.panelOrder.push(newId);
                const panel = new DashboardPanel(newId, { type: 'value', title: '新面板', value: '--' });
                this.panels.set(newId, panel);
                this._render();
                this._mountPanels();
            });
        }
    }

    _bindCloseEvents() {
        this.container?.querySelectorAll('.dashboard-grid__close-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                this.removePanel(btn.dataset.panelId);
            });
        });
    }

    _defaultPanels() {
        return [
            { id: 'altitude', spec: { type: 'altitude_line', title: '高度时序', window: '60s' } },
            { id: 'velocity', spec: { type: 'velocity_line', title: '速度三维', window: '60s' } },
            { id: 'progress', spec: { type: 'value', title: '任务进度', value: 0, unit: '%' } },
        ];
    }
}

export { DashboardGrid };
