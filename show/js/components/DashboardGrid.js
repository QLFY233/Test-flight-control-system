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
            <div class="dashboard-grid" style="grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); grid-auto-rows: minmax(200px, auto);">
                ${this.panelOrder.map((id, i) => `
                    <div class="dashboard-grid__cell" data-panel-id="${id}" draggable="true" style="border:var(--border-hair);background:var(--color-surface);min-height:180px;display:flex;flex-direction:column;position:relative;">
                        <div class="dashboard-grid__drag-handle" style="cursor:grab;padding:2px 6px;text-align:center;color:var(--color-text-disabled);font-family:var(--font-mono);font-size:var(--text-2xs);border-bottom:var(--border-hair);" title="DRAG">:::</div>
                        <div class="dashboard-grid__panel-content" style="flex:1;min-height:0;" id="dash-panel-${id}"></div>
                        <button class="dashboard-grid__close-btn" data-panel-id="${id}" style="position:absolute;top:2px;right:4px;background:none;border:none;color:var(--color-text-disabled);cursor:pointer;font-family:var(--font-mono);font-size:var(--text-xs);padding:2px;">×</button>
                    </div>
                `).join('')}
                <div class="dashboard-grid__add-cell" style="border:1px dashed var(--color-border);min-height:180px;display:flex;align-items:center;justify-content:center;cursor:pointer;color:var(--color-text-disabled);font-family:var(--font-mono);font-size:var(--text-xs);letter-spacing:var(--track-wide);transition:all var(--duration-fast) var(--ease-out-expo);">
                    [ + ADD PANEL ]
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
                cell.style.borderColor = '#FF2A2A';
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
            { id: 'altitude', spec: { type: 'altitude_line', title: 'ALTITUDE · 高度时序', window: '60s' } },
            { id: 'velocity', spec: { type: 'velocity_line', title: 'VELOCITY · 速度三维', window: '60s' } },
            { id: 'accel', spec: { type: 'accel_line', title: 'ACCEL · 加速度', window: '60s' } },
            { id: 'progress', spec: { type: 'value', title: 'PROGRESS · 任务进度', value: 47.2, unit: '%' } },
            { id: 'anomalies', spec: { type: 'bar', title: 'ANOMALIES · 异常统计', window: '24h' } },
            { id: 'altitude_val', spec: { type: 'value', title: 'ALT · 当前高度', value: 28.7, unit: 'm' } },
            { id: 'speed_val', spec: { type: 'value', title: 'SPD · 当前速度', value: 1.43, unit: 'm/s' } },
        ];
    }
}

export { DashboardGrid };
