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
        this._boundOnAlphaOutput = this._onAlphaOutput.bind(this);
        this._unsubTrajectory = null;
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
        bus.off('alpha-output', this._boundOnAlphaOutput);
        if (this._unsubTrajectory) { this._unsubTrajectory(); this._unsubTrajectory = null; }
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
                <div class="card">
                    <div class="card__inner">
                        <div class="card__header"><span class="card__header-accent">[ α OUT ]</span> Alpha 实时输出
                            <button type="button" class="btn btn--ghost btn--sm" id="alpha-output-clear" title="清空输出流">CLEAR</button>
                        </div>
                        <div class="card__body">
                            <div class="alpha-page__alpha-output" id="alpha-output-stream">
                                <div class="alpha-out__hint">/// WAITING α OUTPUT</div>
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
        // α 实时输出流 (WS alpha_output → app.js → bus)
        bus.on('alpha-output', this._boundOnAlphaOutput);

        // 清空按钮 + 恢复上下文: 当前计划作为首条记录 (页面刷新后)
        const clearBtn = this.container?.querySelector('#alpha-output-clear');
        if (clearBtn) {
            clearBtn.addEventListener('click', () => {
                const c = this.container?.querySelector('#alpha-output-stream');
                if (c) {
                    c.innerHTML = '';
                    this._appendAlphaHint(c);
                }
            });
        }
        this._initAlphaStream();

        // 恢复上下文: 刷新/恢复任务后 actionSequence 异步载入 → 流为空时补首条
        // (仅响应 actionSequence 路径变更, 忽略 10Hz 遥测轨迹更新)
        this._unsubTrajectory = store.subscribe('trajectory', (v, o, path) => {
            if (path !== 'trajectory.actionSequence') return;
            const stream = this.container?.querySelector('#alpha-output-stream');
            if (stream && !stream.querySelector('.alpha-out__entry')) {
                const seq = store.get('trajectory.actionSequence') || [];
                if (seq.length) this._appendAlphaEntry(seq);
            }
        });
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

    // ── α 实时输出流 ([ α OUT ] 卡片, 可滚动) ──

    /**
     * 接收 α 产出广播 (bus 'alpha-output', 源: WS alpha_output)。
     * 动作序列提取优先级: remaining_actions → action.actions → actions。
     */
    _onAlphaOutput(payload) {
        if (!payload) return;
        const actions = Array.isArray(payload.remaining_actions) ? payload.remaining_actions
            : (Array.isArray(payload.action && payload.action.actions) ? payload.action.actions
            : (Array.isArray(payload.actions) ? payload.actions : []));
        if (!actions.length) return;
        this._appendAlphaEntry(actions);
    }

    /** 动作序列 → 紧凑文本: takeoff → goto(3.0,2.0,1.0) 1.5m */
    _formatActionSeq(actions) {
        return actions.map(a => {
            const code = (a && a.code) || 'ACT_';
            let s = code;
            const t = a.target;
            if (Array.isArray(t) && t.length >= 3) {
                s += `(${t.slice(0, 3).map(v => (typeof v === 'number' ? v.toFixed(1) : v)).join(',')})`;
            } else if (t && typeof t === 'object' && typeof t.x === 'number') {
                s += `(${t.x.toFixed(1)},${t.y.toFixed(1)},${t.z.toFixed(1)})`;
            }
            if (a.value != null) s += ` ${a.value}${a.units || ''}`;
            return s;
        }).join(' → ');
    }

    /** 追加一条 α 输出记录 (去重 + 上限 60 条 + 智能跟随滚动) */
    _appendAlphaEntry(actions) {
        const container = this.container?.querySelector('#alpha-output-stream');
        if (!container) return;
        const seqText = this._formatActionSeq(actions);
        // WS 广播含执行中剩余序列 (每 2s 心跳重复) → 与末条相同则跳过
        const last = container.querySelector('.alpha-out__entry:last-child .alpha-out__body');
        if (last && last.textContent === seqText) return;

        // 移除等待提示
        const hint = container.querySelector('.alpha-out__hint');
        if (hint) hint.remove();

        const now = new Date();
        const pad = (n) => String(n).padStart(2, '0');
        const ts = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;

        const entry = document.createElement('div');
        entry.className = 'alpha-out__entry';
        entry.innerHTML = `
            <div class="alpha-out__meta">${ts} · [α] ${actions.length} ACTIONS</div>
            <div class="alpha-out__body">${esc(seqText)}</div>
        `;
        container.appendChild(entry);

        // 上限 60 条: 移除最旧
        while (container.children.length > 60) container.removeChild(container.firstChild);

        // 用户已滚到底部附近才自动跟随 (上滚查看历史时不打扰)
        const nearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 40;
        if (nearBottom) container.scrollTop = container.scrollHeight;
    }

    _appendAlphaHint(container) {
        if (!container || container.querySelector('.alpha-out__hint')) return;
        const hint = document.createElement('div');
        hint.className = 'alpha-out__hint';
        hint.textContent = '/// WAITING α OUTPUT';
        container.appendChild(hint);
    }

    /** 页面刷新后恢复: 当前计划 (trajectory.actionSequence) 作为首条记录 */
    _initAlphaStream() {
        const seq = store.get('trajectory.actionSequence') || [];
        if (seq.length) this._appendAlphaEntry(seq);
    }
}

export { AlphaPage };
