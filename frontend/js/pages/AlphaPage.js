/**
 * AlphaPage — Main flight control view.
 * Left panel: environment info + task progress (no chat)
 * Right panel: ViewModeSelector + ViewPanels (3D/video/charts)
 * FloatingBall integration
 * WS handlers: pose, status, alpha_output, alert
 */

import store from '../state.js';
import bus from '../event-bus.js';
import { renderTwoColumn, wsManager } from '../shared.js';
import { ViewModeSelector } from '../components/ViewModeSelector.js';
import { ViewPanel } from '../components/ViewPanel.js';
import { esc } from '../escape.js';

class AlphaPage {
    constructor() {
        this.container = null;
        this.title = '飞控';
        this.viewPanels = [];
        this.viewModeSelector = null;
        this._boundOnViewModeChanged = this._onViewModeChanged.bind(this);
        this._boundOnViewSourceChanged = this._onViewSourceChanged.bind(this);
        this._boundOnAlert = this._onAlert.bind(this);
    }

    mount(container) {
        this.container = container;
        this.render();
        this._setupSubscriptions();
    }

    unmount() {
        this.viewPanels.forEach(vp => vp.unmount && vp.unmount());
        this.viewPanels = [];
        bus.off('view-mode-changed', this._boundOnViewModeChanged);
        bus.off('view-source-changed', this._boundOnViewSourceChanged);
        bus.off('alert', this._boundOnAlert);
        this.container = null;
    }

    render() {
        const env = store.get('environment');
        const flight = store.get('flight');

        // Left panel: environment + task progress
        const leftHtml = `
            <div class="alpha-page">
                <div class="card">
                    <div class="card__inner">
                        <div class="card__header"><span class="card__header-accent">[ ENV ]</span> 环境信息</div>
                        <div class="card__body">
                            <div class="alpha-page__env-info">
                                <div class="alpha-page__env-item">
                                    <span class="alpha-page__env-label">TEMP</span>
                                    <span class="alpha-page__env-value">${env.temperature ?? '--'} °C</span>
                                </div>
                                <div class="alpha-page__env-item">
                                    <span class="alpha-page__env-label">HUM</span>
                                    <span class="alpha-page__env-value">${env.humidity ?? '--'} %</span>
                                </div>
                            <div class="alpha-page__env-item">
                                <span class="alpha-page__env-label">WIND</span>
                                <span class="alpha-page__env-value">${env.windSpeed ?? '--'} m/s</span>
                            </div>
                            <div class="alpha-page__env-item">
                                <span class="alpha-page__env-label">DIR</span>
                                <span class="alpha-page__env-value">${env.windDirection ?? '--'}°</span>
                            </div>
                            <div class="alpha-page__env-item">
                                <span class="alpha-page__env-label">PRES</span>
                                <span class="alpha-page__env-value">${env.pressure ?? '--'} hPa</span>
                            </div>
                            <div class="alpha-page__env-item">
                                <span class="alpha-page__env-label">LOC</span>
                                <span class="alpha-page__env-value">${esc(env.location || '--')}</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

                <div class="card">
                    <div class="card__inner">
                        <div class="card__header"><span class="card__header-accent">[ TASK ]</span> 任务进度</div>
                        <div class="card__body">
                            <div class="alpha-page__task-progress">
                                <div class="alpha-page__task-title">
                                    ${esc(flight.taskTitle || 'NO TASK')}
                                </div>
                                <div class="progress-bar" style="margin-bottom: var(--space-3);">
                                    <div class="progress-bar__fill" style="width: ${flight.progress || 0}%"></div>
                                </div>
                                <div style="font-size: var(--text-sm); color: var(--color-text-secondary); margin-bottom: var(--space-3);">
                                    ${flight.currentActionCode ? `[${esc(flight.currentActionCode)}] ${flight.currentAction}/${flight.totalActions || 0}` : (flight.currentAction > 0 ? `ACTION ${flight.currentAction}/${flight.totalActions || 0}` : 'STANDBY')}
                                    ${flight.currentActionParams ? `<br><span style="font-family:var(--font-mono);font-size:var(--text-xs);color:var(--color-text-disabled);">PARAMS: ${esc(JSON.stringify(flight.currentActionParams))}</span>` : ''}
                                </div>
                                <div style="font-size: var(--text-sm); color: var(--color-text-secondary);">
                                    MODE: ${esc(flight.mode || '--')}
                                    &nbsp;|&nbsp;STATUS: ${esc(flight.status || 'idle')}
                                </div>
                                <div class="alpha-page__action-list" style="margin-top: var(--space-2);">
                                    ${(store.get('trajectory.actionSequence') || []).slice(0, 10).map((a, i) => `
                                        <div class="alpha-page__action-item ${i === (flight.currentAction || 0) ? 'alpha-page__action-item--active' : ''}">
                                            ${i === (flight.currentAction || 0) ? '>>>' : ' · '} ${esc(a.code || 'ACT_')}${a.params && a.params.target ? ` → (${esc(a.params.target.x?.toFixed(1) || '?')}, ${esc(a.params.target.y?.toFixed(1) || '?')}, ${esc(a.params.target.z?.toFixed(1) || '?')})` : ''}
                                        </div>
                                    `).join('') || ''}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;

        // Use renderTwoColumn helper
        renderTwoColumn(this.container, leftHtml, '', '/// ALPHA FLIGHT CONTROL');

        // Right toolbar: view mode selector
        const toolbarEl = document.getElementById('right-toolbar');
        if (toolbarEl) {
            this.viewModeSelector = new ViewModeSelector(toolbarEl);
            this.viewModeSelector.render();
        }

        // Right view area
        const viewArea = document.getElementById('right-view-area');
        if (viewArea) {
            this._setupViews(viewArea);
        }
    }

    _setupViews(viewArea) {
        // Clear is handled by renderTwoColumn

        const ui = store.get('ui');
        const mode = ui.viewMode || 1;
        const sources = ui.viewSources || ['chart'];

        viewArea.className = 'right-column__view-area';
        if (mode === 1) viewArea.classList.add('right-column__view-area--single');
        else if (mode === 2) viewArea.classList.add('right-column__view-area--double');
        else if (mode === 3) viewArea.classList.add('right-column__view-area--triple');

        this.viewPanels.forEach(vp => vp.unmount && vp.unmount());
        this.viewPanels = [];

        for (let i = 0; i < mode; i++) {
            const source = sources[i] || 'chart';
            const panelEl = document.createElement('div');
            panelEl.style.flex = '1';
            panelEl.style.minWidth = '0';
            panelEl.style.minHeight = '0';
            panelEl.style.border = '1px solid var(--color-border)';
            panelEl.style.position = 'relative';
            viewArea.appendChild(panelEl);

            const vp = new ViewPanel(i, source);
            vp.mount(panelEl);
            this.viewPanels.push(vp);
        }
    }

    _setupSubscriptions() {
        bus.on('view-mode-changed', this._boundOnViewModeChanged);
        bus.on('view-source-changed', this._boundOnViewSourceChanged);
        bus.on('alert', this._boundOnAlert);
    }

    _onViewModeChanged({ mode, sources }) {
        const viewArea = document.getElementById('right-view-area');
        if (!viewArea) return;

        // Re-initialize views
        this._refreshViews(viewArea);
    }

    _onViewSourceChanged({ slot, source, chartType }) {
        if (this.viewPanels[slot]) {
            this.viewPanels[slot].setSource(source, chartType);
        }
    }

    _refreshViews(viewArea) {
        viewArea.innerHTML = '';
        const ui = store.get('ui');
        const mode = ui.viewMode || 1;
        const sources = ui.viewSources || ['chart'];

        viewArea.className = 'right-column__view-area';
        if (mode === 1) viewArea.classList.add('right-column__view-area--single');
        else if (mode === 2) viewArea.classList.add('right-column__view-area--double');
        else if (mode === 3) viewArea.classList.add('right-column__view-area--triple');

        this.viewPanels.forEach(vp => vp.unmount && vp.unmount());
        this.viewPanels = [];

        for (let i = 0; i < mode; i++) {
            const source = sources[i] || 'chart';
            const panelEl = document.createElement('div');
            panelEl.style.cssText = 'flex: 1; min-width: 0; min-height: 0; border: 1px solid var(--color-border); position: relative;';
            viewArea.appendChild(panelEl);

            const vp = new ViewPanel(i, source);
            vp.mount(panelEl);
            this.viewPanels.push(vp);
        }
    }

    _onAlert(payload) {
        if (!payload) return;
        // Alerts are shown as toasts (handled in app.js via bus)
        // This is a hook for page-specific alert handling if needed
    }
}

export { AlphaPage };
