/**
 * OverviewPage — Dashboard page.
 * System status indicators, recent sessions, environment summary, new flight button.
 */

import store from '../state.js';
import bus from '../event-bus.js';
import { apiManager, router } from '../shared.js';
import { SessionCard } from '../components/SessionCard.js';
import { EmptyState } from '../components/EmptyState.js';

class OverviewPage {
    constructor() {
        this.container = null;
        this.title = '总览';
    }

    mount(container) {
        this.container = container;
        this.render();
        this._loadData();
    }

    unmount() {
        this.container = null;
    }

    render() {
        const conn = store.get('connection');
        const env = store.get('environment');

        // Status indicators
        const indicators = [
            { label: 'Backend A', status: conn.backendA || 'unknown' },
            { label: 'Backend B', status: conn.backendB || 'unknown' },
            { label: 'Drone', status: conn.drone || 'unknown' },
            { label: 'LLM', status: conn.llm || 'unknown' },
        ];

        const getDotClass = (status) => {
            if (status === 'ok' || status === 'connected') return 'indicator-light__dot--green';
            if (status === 'connecting' || status === 'warning') return 'indicator-light__dot--yellow';
            return 'indicator-light__dot--red';
        };

        const getStatusText = (status) => {
            const map = { ok: 'OK', connected: 'ONLINE', connecting: 'CONN', warning: 'WARN', error: 'ERR', unknown: 'UNK' };
            return map[status] || status.toUpperCase();
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
                    <div class="indicator-grid">
                        ${indicators.map(ind => `
                            <div class="indicator-light">
                                <div class="indicator-light__dot ${getDotClass(ind.status)}"></div>
                                <div>
                                    <div class="indicator-light__label">${ind.label}</div>
                                    <div class="indicator-light__status">${getStatusText(ind.status)}</div>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                </div>

                <div class="overview-page__section">
                    <div class="overview-page__section-title">[ 环境概要 ]</div>
                    <div class="overview-page__env-cards">
                        <div class="overview-page__env-card">
                            <div class="overview-page__env-card-value">${env.temperature ?? '--'}°</div>
                            <div class="overview-page__env-card-label">TEMP · 温度</div>
                        </div>
                        <div class="overview-page__env-card">
                            <div class="overview-page__env-card-value">${env.humidity ?? '--'}%</div>
                            <div class="overview-page__env-card-label">HUM · 湿度</div>
                        </div>
                        <div class="overview-page__env-card">
                            <div class="overview-page__env-card-value">${env.windSpeed ?? '--'}</div>
                            <div class="overview-page__env-card-label">WIND · 风速 m/s</div>
                        </div>
                    </div>
                </div>

                <div class="overview-page__section">
                    <div class="overview-page__section-title">[ 最近任务 ]</div>
                    <div id="recent-sessions" class="overview-page__recent-grid">
                        <div style="font-family:var(--font-mono);font-size:var(--text-xs);color:var(--color-text-disabled);letter-spacing:var(--track-wide);padding:var(--space-4);">/// LOADING...</div>
                    </div>
                </div>
            </div>
        `;

        // Center the page (previously used left-column, now full-width for overview)
        this.container.style.width = '100%';
        this.container.style.borderRight = 'none';
        this.container.style.overflow = 'hidden';
        this.container.style.display = 'flex';
        this.container.style.flexDirection = 'column';
    }

    async _loadData() {
        try {
            const sessions = await apiManager.getSessions({ limit: 6 });
            const sessionsData = Array.isArray(sessions) ? sessions : (sessions?.sessions || sessions?.data || []);

            const grid = this.container?.querySelector('#recent-sessions');
            if (!grid) return;

            if (sessionsData.length === 0) {
                const emptyState = new EmptyState({
                    icon: '📋',
                    title: '暂无任务记录',
                    desc: '点击下方按钮开始一个新的试飞任务',
                });
                grid.innerHTML = '';
                grid.appendChild(emptyState.render());
            } else {
                grid.innerHTML = '';
                for (const session of sessionsData) {
                    const card = new SessionCard(session, {
                        onClick: (s) => {
                            router.navigate('#/history');
                            store.set('history.selectedSession', s);
                        },
                    });
                    grid.appendChild(card.render());
                }
            }
        } catch (e) {
            console.warn('[OverviewPage] could not load sessions:', e.message);
            const grid = this.container?.querySelector('#recent-sessions');
            if (grid) {
                grid.innerHTML = '<div style="color: var(--color-error); padding: var(--space-lg);">加载失败: ' + e.message + '</div>';
            }
        }
    }
}

export { OverviewPage };
