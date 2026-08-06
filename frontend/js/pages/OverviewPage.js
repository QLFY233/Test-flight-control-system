/**
 * OverviewPage — Dashboard page.
 */

import store from '../state.js';
import bus from '../event-bus.js';
import { apiManager, router } from '../shared.js';
import { TaskCard } from '../components/TaskCard.js';
import { EmptyState } from '../components/EmptyState.js';
import { genScrollWheel } from '../components/ScrollWheel.js';
import { esc } from '../escape.js';

const WHEEL_OPTS = {
    temperature: { vals: (() => { const a = []; for (let t = -10; t <= 50; t++) a.push(t); return a; })(), fmt: v => v },
    humidity: { vals: (() => { const a = []; for (let h = 0; h <= 100; h++) a.push(h); return a; })(), fmt: v => v },
    windSpeed: { vals: (() => { const a = []; for (let w = 0; w <= 20; w += 0.5) a.push(Math.round(w * 10) / 10); return a; })(), fmt: v => v.toFixed(1) },
};

class OverviewPage {
    constructor() {
        this.container = null;
        this.title = '总览';
        this._unsubFlight = null;
        this._boundOnTaskRestored = null;
        this._activeWheel = null;
        this._wheelsDisabled = false;
    }

    mount(container) {
        this.container = container;
        this.render();
        this._bindCards();
        this._loadData();
        // 任务恢复后刷新最近任务 (当前徽标同步)
        this._boundOnTaskRestored = () => this._loadData();
        bus.on('task-restored', this._boundOnTaskRestored);
        this._unsubFlight = store.subscribe('flight', () => {
            const status = store.get('flight.status');
            // 冻结枚举：executing = 任务执行中
            const dis = status === 'executing';
            if (dis !== this._wheelsDisabled) {
                this._wheelsDisabled = dis;
                this._updateCardStates();
            }
        });
    }

    unmount() {
        if (this._boundOnTaskRestored) { bus.off('task-restored', this._boundOnTaskRestored); this._boundOnTaskRestored = null; }
        if (this._unsubFlight) { this._unsubFlight(); this._unsubFlight = null; }
        this._destroyWheel();
        this.container = null;
    }

    render() {
        const conn = store.get('connection');
        const env = store.get('environment');
        const flight = store.get('flight');
        const locked = flight.status === 'executing';

        const indicators = [
            { label: 'Backend A', status: conn.backendA || 'unknown' },
            { label: 'Backend B', status: conn.backendB || 'unknown' },
            { label: 'Drone', status: conn.drone || 'unknown' },
            { label: 'LLM', status: conn.llm || 'unknown' },
        ];

        const getDotClass = s => {
            if (s === 'ok' || s === 'connected' || s === 'up') return 'indicator-light__dot--green';
            if (s === 'connecting' || s === 'warning' || s === 'degraded' || s === 'down') return 'indicator-light__dot--yellow';
            return 'indicator-light__dot--red';
        };
        const getStatusText = s => {
            const m = { ok: 'OK', connected: 'ONLINE', connecting: 'CONN', warning: 'WARN', error: 'ERR', unknown: 'UNK', up: 'UP', down: 'DOWN', degraded: 'DEGRADED' };
            return m[s] || (s || '').toUpperCase();
        };

        this.container.innerHTML = `
            <div class="overview-page">
                <div class="overview-page__hero">
                    <div class="overview-page__hero-tag">/// SYS.REV 2.6</div>
                    <div class="overview-page__hero-title">试飞控制系统</div>
                    <div class="overview-page__hero-sub">TACTICAL FLIGHT TELEMETRY &amp; CONTROL</div>
                </div>
                <div class="overview-page__section">
                    <div class="overview-page__section-title">[ 系统状态 ]</div>
                    <div class="indicator-grid">${indicators.map(i => `<div class="indicator-light"><div class="indicator-light__dot ${getDotClass(i.status)}"></div><div><div class="indicator-light__label">${esc(i.label)}</div><div class="indicator-light__status">${esc(getStatusText(i.status))}</div></div></div>`).join('')}</div>
                </div>
                <div class="overview-page__section">
                    <div class="overview-page__section-title" id="env-section-title">[ 环境概要 ]${locked ? ' <span style="color:var(--color-red);">/// LOCKED — 任务执行中</span>' : ''}</div>
                    <div class="overview-page__env-cards">
                        <div class="overview-page__env-card env-card" data-env="temperature"><div class="overview-page__env-card-value">${env.temperature ?? 25}</div><div class="overview-page__env-card-label">TEMP · 温度</div></div>
                        <div class="overview-page__env-card env-card" data-env="humidity"><div class="overview-page__env-card-value">${env.humidity ?? 60}</div><div class="overview-page__env-card-label">HUM · 湿度</div></div>
                        <div class="overview-page__env-card env-card" data-env="windSpeed"><div class="overview-page__env-card-value">${(env.windSpeed ?? 0).toFixed(1)}</div><div class="overview-page__env-card-label">WIND · 风速 m/s</div></div>
                    </div>
                </div>
                <div class="overview-page__section">
                    <div class="overview-page__section-title">[ 最近任务 ]</div>
                    <div id="recent-sessions" class="overview-page__recent-grid"><div style="font-family:var(--font-mono);font-size:var(--text-xs);color:var(--color-text-disabled);letter-spacing:var(--track-wide);padding:var(--space-4);">/// LOADING...</div></div>
                </div>
            </div>
        `;
        this.container.style.cssText = 'width:100%;overflow:hidden;display:flex;flex-direction:column';
    }

    _bindCards() {
        this.container.querySelectorAll('.env-card').forEach(card => {
            card.addEventListener('click', () => {
                if (this._wheelsDisabled) return;
                this._showWheel(card);
            });
        });
    }

    _showWheel(cardEl) {
        this._destroyWheel();
        const envKey = cardEl.dataset.env;
        const opts = WHEEL_OPTS[envKey];
        if (!opts) return;

        const valEl = cardEl.querySelector('.overview-page__env-card-value');
        if (!valEl) return;

        const initial = store.get(`environment.${envKey}`);
        const w = genScrollWheel(opts.vals, initial, 32, v => {
            store.set(`environment.${envKey}`, v);
            valEl.textContent = opts.fmt(v);
        });

        // Position container
        const container = w.container;
        container.style.position = 'absolute';
        container.style.left = '0';
        container.style.right = '0';
        container.style.zIndex = '10';

        const cr = cardEl.getBoundingClientRect();
        const vr = valEl.getBoundingClientRect();
        const valueCenter = vr.top - cr.top + vr.height / 2;
        // overlay top so that overlay center = value center: overlayTop = valueCenter - 48
        const overlayTop = valueCenter - 48;
        container.style.top = overlayTop + 'px';

        cardEl.style.position = 'relative';
        cardEl.appendChild(container);

        this._activeWheel = { container, cardEl, valEl, envKey, timer: null };
        // 无自动隐藏计时器 — 用户必须点击确认（_resetHideTimer 已废弃删除）
        this._setupWheelClickToClose(container);

        // Re-focus scroll after DOM is attached
        requestAnimationFrame(() => {
            const initIdx = w.values.findIndex(x => Math.abs(x - initial) < 0.01);
            if (w.scroller) {
                w.scroller.scrollTop = Math.max(0, initIdx) * w.itemHeight + w.centeringOffset;
            }
        });
    }

    _setupWheelClickToClose(container) {
        // Clicking the wheel anywhere confirms and hides
        container.addEventListener('click', (e) => {
            e.stopPropagation();
            e.preventDefault();
            this._destroyWheel();
        }, { once: true });
    }

    _destroyWheel() {
        if (!this._activeWheel) return;
        const a = this._activeWheel;
        if (a.timer) clearTimeout(a.timer);
        a.container.remove();
        a.cardEl.style.position = '';
        this._activeWheel = null;
    }

    _updateCardStates() {
        if (this._wheelsDisabled) this._destroyWheel();
        const title = this.container?.querySelector('#env-section-title');
        if (!title) return;
        if (this._wheelsDisabled) {
            if (!title.querySelector('span')) title.innerHTML = title.textContent + ' <span style="color:var(--color-red);">/// LOCKED — 任务执行中</span>';
        } else {
            const span = title.querySelector('span');
            if (span) span.remove();
        }
    }

    async _loadData() {
        try {
            const sessions = await apiManager.getSessions({ limit: 6 });
            const data = Array.isArray(sessions) ? sessions : (sessions?.sessions || sessions?.data || []);
            const grid = this.container?.querySelector('#recent-sessions');
            if (!grid) return;
            if (data.length === 0) {
                const empty = new EmptyState({ title: '暂无任务记录', desc: '点击右上角 [ ☰ 任务 ] 新建任务' });
                grid.innerHTML = ''; grid.appendChild(empty.render());
            } else {
                grid.innerHTML = '';
                const currentId = store.get('flight.sessionId');
                data.forEach(s => {
                    // 统一任务卡片: 名称/状态/时间/对话·数据计数 + 恢复/重命名/删除 (与 AI 任务面板一致)
                    const card = new TaskCard(s, {
                        current: s.id === currentId,
                        onClick: (sess) => { router.navigate('#/history'); store.set('history.selectedSession', sess); },
                        onChanged: () => this._loadData(),
                    });
                    grid.appendChild(card.render());
                });
            }
        } catch (e) {
            console.warn('[OverviewPage] load sessions:', e.message);
            const grid = this.container?.querySelector('#recent-sessions');
            if (grid) grid.innerHTML = '<div style="color:var(--color-red);padding:var(--space-8);font-family:var(--font-mono);font-size:var(--text-xs);">加载失败: ' + esc(e.message) + '</div>';
        }
    }
}

export { OverviewPage };
