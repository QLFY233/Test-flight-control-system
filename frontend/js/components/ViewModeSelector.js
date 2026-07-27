/**
 * ViewModeSelector — Controls the right panel view layout (1/2 views) and per-slot source selection.
 * 3-view mode removed per 2026-07-26 redesign.
 */

import store from '../state.js';
import bus from '../event-bus.js';

class ViewModeSelector {
    constructor(container) {
        this.container = container;
        this.availableSources = ['chart'];
        this.maxMode = 2;
    }

    mount() {
        this.render();
    }

    render() {
        const ui = store.get('ui');
        const viewMode = Math.min(ui.viewMode || 1, this.maxMode);
        const viewSources = ui.viewSources || ['chart'];

        let sourceSelects = '';
        for (let i = 0; i < viewMode; i++) {
            const currentSource = viewSources[i] || 'chart';
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
                </div>
                ${sourceSelects}
            </div>
        `;

        this.container.querySelectorAll('.view-mode-selector__mode-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const mode = parseInt(btn.dataset.mode);
                this._setMode(mode);
            });
        });

        this.container.querySelectorAll('.view-mode-selector__source-select').forEach(sel => {
            sel.addEventListener('change', () => {
                const slot = parseInt(sel.dataset.slot);
                this._setSource(slot, sel.value);
            });
        });
    }

    _setMode(mode) {
        mode = Math.min(mode, this.maxMode);
        let sources = store.get('ui.viewSources') || ['chart'];

        if (mode > sources.length) {
            while (sources.length < mode) {
                sources.push('chart');
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
        const sources = [...(store.get('ui.viewSources') || ['chart'])];

        const conflictSlot = sources.indexOf(source);
        if (conflictSlot >= 0 && conflictSlot !== slot) {
            const temp = sources[slot];
            sources[conflictSlot] = temp || 'chart';
        }

        sources[slot] = source;
        store.set('ui.viewSources', sources);

        bus.emit('view-source-changed', { slot, source });
        this.render();
    }

    _sourceLabel(source) {
        const labels = { 'chart': '图表' };
        return labels[source] || source;
    }
}

export { ViewModeSelector };
