/**
 * BetaPage — Planning & analysis view.
 * Left panel: environment summary (read-only) + flight plan review area
 * Right panel: FieldMap2D (default) or other views
 * Chat accessed via global ChatDock (not embedded)
 */

import store from '../state.js';
import bus from '../event-bus.js';
import { renderTwoColumn, wsManager, sharedTrajectoryLine, sharedWaypointMarker } from '../app.js';
import { ViewModeSelector } from '../components/ViewModeSelector.js';
import { ViewPanel } from '../components/ViewPanel.js';
import { FlightPlanCard } from '../components/FlightPlanCard.js';

class BetaPage {
    constructor() {
        this.container = null;
        this.title = '规划';
        this.viewPanels = [];
        this.viewModeSelector = null;
        this._boundOnPlanReceived = this._onPlanReceived.bind(this);
        this._boundOnViewModeChanged = this._onViewModeChanged.bind(this);
        this._boundOnViewSourceChanged = this._onViewSourceChanged.bind(this);
    }

    mount(container) {
        this.container = container;
        this.render();
        bus.on('plan-received', this._boundOnPlanReceived);
        bus.on('view-mode-changed', this._boundOnViewModeChanged);
        bus.on('view-source-changed', this._boundOnViewSourceChanged);
    }

    unmount() {
        this.viewPanels.forEach(vp => vp.unmount && vp.unmount());
        this.viewPanels = [];
        bus.off('plan-received', this._boundOnPlanReceived);
        bus.off('view-mode-changed', this._boundOnViewModeChanged);
        bus.off('view-source-changed', this._boundOnViewSourceChanged);
        this.container = null;
    }

    render() {
        const env = store.get('environment');
        const beta = store.get('beta');
        const currentPlan = beta?.currentPlan;

        // Left panel: environment summary + plan review
        const leftHtml = `
            <div class="beta-page">
                <div class="card card--raised" style="margin-bottom: var(--space-md);">
                    <div class="card__header">环境概要</div>
                    <div class="card__body">
                        <div class="beta-page__env-summary">
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-xs); font-size: var(--font-sm);">
                                <span style="color: var(--color-text-secondary);">温度:</span>
                                <span>${env.temperature ?? '--'} °C</span>
                                <span style="color: var(--color-text-secondary);">湿度:</span>
                                <span>${env.humidity ?? '--'} %</span>
                                <span style="color: var(--color-text-secondary);">风速:</span>
                                <span>${env.windSpeed ?? '--'} m/s, ${env.windDirection ?? '--'}°</span>
                                <span style="color: var(--color-text-secondary);">地点:</span>
                                <span>${env.location || '--'}</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="card card--raised" style="flex: 1; overflow-y: auto;">
                    <div class="card__header">飞行计划</div>
                    <div class="card__body" id="beta-plan-area">
                        ${currentPlan ? '' : `
                            <div class="beta-page__chat-hint">
                                使用右下角 <strong style="color: var(--color-cyan);">Beta 对话</strong> 与 AI 助手沟通生成飞行计划
                            </div>
                        `}
                    </div>
                </div>
            </div>
        `;

        const mainContent = document.getElementById('main-content');
        renderTwoColumn(mainContent, leftHtml, '', 'Beta 规划');

        // Right panel: FieldMap2D by default
        const toolbarEl = document.getElementById('right-toolbar');
        if (toolbarEl) {
            this.viewModeSelector = new ViewModeSelector(toolbarEl);
            this.viewModeSelector.render();
        }

        const viewArea = document.getElementById('right-view-area');
        if (viewArea) {
            this._setupViews(viewArea);
        }

        // Render plan if available
        if (currentPlan) {
            this._renderPlan(currentPlan);
        }
    }

    _setupViews(viewArea) {
        viewArea.innerHTML = '';
        const ui = store.get('ui');
        const mode = ui.viewMode || 1;
        const sources = ui.viewSources || ['chart'];

        viewArea.className = 'right-column__view-area';
        if (mode === 1) viewArea.classList.add('right-column__view-area--single');
        else if (mode === 2) viewArea.classList.add('right-column__view-area--double');
        else viewArea.classList.add('right-column__view-area--triple');

        this.viewPanels.forEach(vp => vp.unmount && vp.unmount());
        this.viewPanels = [];

        for (let i = 0; i < mode; i++) {
            const source = sources[i] || 'chart';
            const panelEl = document.createElement('div');
            panelEl.style.cssText = 'flex: 1; min-width: 0; min-height: 0; border: 1px solid var(--color-border); position: relative;';
            viewArea.appendChild(panelEl);

            const vp = new ViewPanel(i, source, 'fieldmap');
            vp.mount(panelEl);
            this.viewPanels.push(vp);
        }
    }

    _renderPlan(plan) {
        const planArea = document.getElementById('beta-plan-area');
        if (!planArea) return;

        planArea.innerHTML = '';

        const flightPlanCard = new FlightPlanCard(plan, {
            onApprove: (p) => {
                wsManager.send('approve_plan', { plan: p });
                planArea.innerHTML = '<div style="padding: var(--space-lg); color: var(--color-success); text-align: center;">计划已批准 ✓</div>';
            },
            onModify: (p) => {
                wsManager.send('modify_plan', { plan: p });
            },
            onReject: (p) => {
                wsManager.send('reject_plan', { plan: p });
                planArea.innerHTML = '<div style="padding: var(--space-lg); color: var(--color-error); text-align: center;">计划已驳回</div>';
            },
            onOverlay3D: (p) => {
                // Set planned trajectory on 3D
                if (p.segments) {
                    const allWaypoints = [];
                    p.segments.forEach(seg => {
                        if (seg.waypoints) allWaypoints.push(...seg.waypoints);
                    });
                    sharedTrajectoryLine.setPlanned(allWaypoints);
                    sharedWaypointMarker.setWaypoints(allWaypoints);
                    store.set('beta.fieldOverlay', true);
                }
            },
        });

        flightPlanCard.mount(planArea);
    }

    _onPlanReceived(plan) {
        store.set('beta.currentPlan', plan);
        const planArea = document.getElementById('beta-plan-area');
        if (planArea) {
            this._renderPlan(plan);
        }
    }

    _onViewModeChanged({ mode, sources }) {
        const viewArea = document.getElementById('right-view-area');
        if (!viewArea) return;
        this.viewPanels.forEach(vp => vp.unmount && vp.unmount());
        this.viewPanels = [];
        viewArea.innerHTML = '';

        viewArea.className = 'right-column__view-area';
        if (mode === 1) viewArea.classList.add('right-column__view-area--single');
        else if (mode === 2) viewArea.classList.add('right-column__view-area--double');
        else viewArea.classList.add('right-column__view-area--triple');

        for (let i = 0; i < mode; i++) {
            const source = sources[i] || 'chart';
            const panelEl = document.createElement('div');
            panelEl.style.cssText = 'flex: 1; min-width: 0; min-height: 0; border: 1px solid var(--color-border); position: relative;';
            viewArea.appendChild(panelEl);

            const vp = new ViewPanel(i, source, 'fieldmap');
            vp.mount(panelEl);
            this.viewPanels.push(vp);
        }
    }

    _onViewSourceChanged({ slot, source }) {
        if (this.viewPanels[slot]) {
            this.viewPanels[slot].setSource(source, 'fieldmap');
        }
    }
}

export { BetaPage };
