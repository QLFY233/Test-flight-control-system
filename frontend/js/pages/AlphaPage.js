/**
 * AlphaPage — Main flight control view.
 * Left panel: environment info + task progress (no chat)
 * Right panel: ViewModeSelector + ViewPanels (3D/video/charts)
 * FloatingBall integration
 * WS handlers: pose, status, alpha_output, alert
 */

import store from '../state.js';
import bus from '../event-bus.js';
import { renderTwoColumn, wsManager, sharedDroneModel, sharedTrajectoryLine, sharedWaypointMarker, sharedFieldRenderer } from '../app.js';
import { ViewModeSelector } from '../components/ViewModeSelector.js';
import { ViewPanel } from '../components/ViewPanel.js';
import { FloatingBall } from '../components/FloatingBall.js';

class AlphaPage {
    constructor() {
        this.container = null;
        this.title = '飞控';
        this.viewPanels = [];
        this.viewModeSelector = null;
        this.floatingBall = null;
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
        if (this.floatingBall && this.floatingBall._collapsed) this.floatingBall._collapse();
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
                <div class="card card--raised" style="margin-bottom: var(--space-md);">
                    <div class="card__header">环境信息</div>
                    <div class="card__body">
                        <div class="alpha-page__env-info">
                            <div class="alpha-page__env-item">
                                <span class="alpha-page__env-label">温度</span>
                                <span class="alpha-page__env-value">${env.temperature ?? '--'} °C</span>
                            </div>
                            <div class="alpha-page__env-item">
                                <span class="alpha-page__env-label">湿度</span>
                                <span class="alpha-page__env-value">${env.humidity ?? '--'} %</span>
                            </div>
                            <div class="alpha-page__env-item">
                                <span class="alpha-page__env-label">风速</span>
                                <span class="alpha-page__env-value">${env.windSpeed ?? '--'} m/s</span>
                            </div>
                            <div class="alpha-page__env-item">
                                <span class="alpha-page__env-label">风向</span>
                                <span class="alpha-page__env-value">${env.windDirection ?? '--'}°</span>
                            </div>
                            <div class="alpha-page__env-item">
                                <span class="alpha-page__env-label">气压</span>
                                <span class="alpha-page__env-value">${env.pressure ?? '--'} hPa</span>
                            </div>
                            <div class="alpha-page__env-item">
                                <span class="alpha-page__env-label">地点</span>
                                <span class="alpha-page__env-value">${env.location || '--'}</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="card card--raised" style="flex: 1; overflow-y: auto;">
                    <div class="card__header">任务进度</div>
                    <div class="card__body">
                        <div class="alpha-page__task-progress">
                            <div class="alpha-page__task-title">
                                ${flight.taskTitle || '无任务'}
                            </div>
                            <div class="progress-bar" style="margin-bottom: var(--space-md);">
                                <div class="progress-bar__fill progress-bar__fill--cyan" style="width: ${flight.progress || 0}%"></div>
                            </div>
                            <div style="font-size: var(--font-sm); color: var(--color-text-secondary); margin-bottom: var(--space-md);">
                                ${flight.currentAction || '待命'}
                            </div>
                            <div style="font-size: var(--font-sm); color: var(--color-text-secondary);">
                                段: ${flight.currentSegment || 0} / ${flight.totalSegments || 0}
                                &nbsp;|&nbsp;模式: ${flight.mode || '--'}
                                &nbsp;|&nbsp;状态: ${flight.status || 'idle'}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;

        // Use renderTwoColumn helper
        const mainContent = document.getElementById('main-content');
        renderTwoColumn(mainContent, leftHtml, '', 'Alpha 飞控');

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

        // FloatingBall
        const fbContainer = document.getElementById('floating-ball-container');
        if (fbContainer) {
            this.floatingBall = new FloatingBall(fbContainer);
            this.floatingBall.mount();
        }
    }

    _setupViews(viewArea) {
        // Clear is handled by renderTwoColumn

        const ui = store.get('ui');
        const mode = ui.viewMode || 1;
        const sources = ui.viewSources || ['3d'];

        viewArea.className = 'right-column__view-area';
        if (mode === 1) viewArea.classList.add('right-column__view-area--single');
        else if (mode === 2) viewArea.classList.add('right-column__view-area--double');
        else if (mode === 3) viewArea.classList.add('right-column__view-area--triple');

        this.viewPanels.forEach(vp => vp.unmount && vp.unmount());
        this.viewPanels = [];

        for (let i = 0; i < mode; i++) {
            const source = sources[i] || '3d';
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
        const sources = ui.viewSources || ['3d'];

        viewArea.className = 'right-column__view-area';
        if (mode === 1) viewArea.classList.add('right-column__view-area--single');
        else if (mode === 2) viewArea.classList.add('right-column__view-area--double');
        else if (mode === 3) viewArea.classList.add('right-column__view-area--triple');

        this.viewPanels.forEach(vp => vp.unmount && vp.unmount());
        this.viewPanels = [];

        for (let i = 0; i < mode; i++) {
            const source = sources[i] || '3d';
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
