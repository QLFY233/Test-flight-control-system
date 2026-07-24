/**
 * ViewModeSelector — Controls the right panel view layout (1/2/3 views) and per-slot source selection.
 */

import store from '../state.js';
import bus from '../event-bus.js';

class ViewModeSelector {
    /**
     * @param {HTMLElement} container
     */
    constructor(container) {
        this.container = container;
        this.availableSources = ['3d', 'video', 'chart'];
    }

    mount() {
        this.render();
    }

    render() {
        const ui = store.get('ui');
        const viewMode = ui.viewMode || 1;
        const viewSources = ui.viewSources || ['3d'];

        let sourceSelects = '';
        for (let i = 0; i < viewMode; i++) {
            const currentSource = viewSources[i] || this.availableSources[0];
            sourceSelects += `
                <select class="view-mode-selector__source-select" data-slot="${i}">
                    ${this.availableSources.map(s => `
                        <option value="${s}" ${s === currentSource ? 'selected' : ''}>${this._sourceLabel(s)}</option>
                    `).join('')}
                </select>
            `;
        }

        this.container.innerHTML = `
            <div class="view-mode-selector">
                <div class="view-mode-selector__modes">
                    <button class="view-mode-selector__mode-btn ${viewMode === 1 ? 'view-mode-selector__mode-btn--active' : ''}" data-mode="1">1视图</button>
                    <button class="view-mode-selector__mode-btn ${viewMode === 2 ? 'view-mode-selector__mode-btn--active' : ''}" data-mode="2">2视图</button>
                    <button class="view-mode-selector__mode-btn ${viewMode === 3 ? 'view-mode-selector__mode-btn--active' : ''}" data-mode="3">3视图</button>
                </div>
                ${sourceSelects}
            </div>
        `;

        // Bind mode buttons
        this.container.querySelectorAll('.view-mode-selector__mode-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const mode = parseInt(btn.dataset.mode);
                this._setMode(mode);
            });
        });

        // Bind source selects
        this.container.querySelectorAll('.view-mode-selector__source-select').forEach(sel => {
            sel.addEventListener('change', () => {
                const slot = parseInt(sel.dataset.slot);
                this._setSource(slot, sel.value);
            });
        });
    }

    _setMode(mode) {
        let sources = store.get('ui.viewSources') || ['3d'];

        if (mode > sources.length) {
            // Add default sources for new slots
            while (sources.length < mode) {
                const nextSource = this.availableSources.find(s => !sources.includes(s)) || this.availableSources[0];
                sources.push(nextSource);
            }
        } else if (mode < sources.length) {
            sources = sources.slice(0, mode);
        }

        store.set('ui.viewMode', mode);
        store.set('ui.viewSources', sources);

        bus.emit('view-mode-changed', { mode, sources });
        this.render();
    }

    _setSource(slot, source) {
        const sources = [...(store.get('ui.viewSources') || ['3d'])];

        // Prevent duplicate sources
        const conflictSlot = sources.indexOf(source);
        if (conflictSlot >= 0 && conflictSlot !== slot) {
            // Swap
            const temp = sources[slot];
            sources[conflictSlot] = temp || this.availableSources.find(s => s !== source && !sources.includes(s)) || this.availableSources[0];
        }

        sources[slot] = source;
        store.set('ui.viewSources', sources);

        bus.emit('view-source-changed', { slot, source });
        this.render();
    }

    _sourceLabel(source) {
        const labels = { '3d': '3D场景', 'video': '视频', 'chart': '图表' };
        return labels[source] || source;
    }
}

export { ViewModeSelector };
