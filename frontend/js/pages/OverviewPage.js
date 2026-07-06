/**
 * OverviewPage — Dashboard page.
 * System status indicators, recent sessions, environment summary, new flight button.
 */

import store from '../state.js';
import bus from '../event-bus.js';
import { apiManager, router } from '../app.js';
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
            const map = { ok: '正常', connected: '已连接', connecting: '连接中', warning: '警告', error: '异常', unknown: '未知' };
            return map[status] || status;
        };

        this.container.innerHTML = `
            <div class="overview-page">
                <div class="overview-page__section">
                    <div class="overview-page__section-title">系统状态</div>
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

                <div class="overview-page__section" style="flex: 1; overflow-y: auto;">
                    <div class="overview-page__section-title">环境概要</div>
                    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--space-md); margin-bottom: var(--space-lg);">
                        <div class="card card--raised" style="padding: var(--space-md); text-align: center;">
                            <div style="font-size: var(--font-2xl); color: var(--color-cyan);">${env.temperature ?? '--'}°C</div>
                            <div style="font-size: var(--font-sm); color: var(--color-text-secondary); margin-top: var(--space-xs);">温度</div>
                        </div>
                        <div class="card card--raised" style="padding: var(--space-md); text-align: center;">
                            <div style="font-size: var(--font-2xl); color: var(--color-cyan);">${env.humidity ?? '--'}%</div>
                            <div style="font-size: var(--font-sm); color: var(--color-text-secondary); margin-top: var(--space-xs);">湿度</div>
                        </div>
                        <div class="card card--raised" style="padding: var(--space-md); text-align: center;">
                            <div style="font-size: var(--font-2xl); color: var(--color-cyan);">${env.windSpeed ?? '--'} m/s</div>
                            <div style="font-size: var(--font-sm); color: var(--color-text-secondary); margin-top: var(--space-xs);">风速</div>
                        </div>
                    </div>

                    <div class="overview-page__section-title">最近任务</div>
                    <div id="recent-sessions" class="overview-page__recent-grid">
                        <div style="color: var(--color-text-disabled); padding: var(--space-lg);">加载中...</div>
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
