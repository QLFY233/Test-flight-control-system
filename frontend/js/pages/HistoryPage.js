/**
 * HistoryPage — History browser with session list, filters, and playback.
 * Left: two sub-tabs (by flight / by data type), filters, session list with multi-select.
 * Right: selected session detail + analysis summary + TimelineControl + playback chart.
 */

import store from '../state.js';
import bus from '../event-bus.js';
import { apiManager, sharedTrajectoryLine, sharedWaypointMarker } from '../shared.js';
import { SessionCard } from '../components/SessionCard.js';
import { TimelineControl } from '../components/TimelineControl.js';
import { ViewPanel } from '../components/ViewPanel.js';
import { EmptyState } from '../components/EmptyState.js';

class HistoryPage {
    constructor() {
        this.container = null;
        this.title = '历史';
        this.sessions = [];
        this.selectedSessions = new Set();
        this.activeSubTab = 'flight'; // 'flight' | 'data'
        this.timelineControl = null;
        this.historyChartPanel = null;
    }

    mount(container) {
        this.container = container;
        this.render();
        this._loadSessions();
    }

    unmount() {
        if (this.timelineControl) this.timelineControl = null;
        if (this.historyChartPanel) { this.historyChartPanel.unmount(); this.historyChartPanel = null; }
        this.container = null;
    }

    render() {
        this.container.innerHTML = `
            <div class="history-page">
                <div class="history-page__left">
                    <div class="tabs" id="history-sub-tabs">
                        <div class="tabs__tab ${this.activeSubTab === 'flight' ? 'tabs__tab--active' : ''}" data-tab="flight">
                            按任务
                        </div>
                        <div class="tabs__tab ${this.activeSubTab === 'data' ? 'tabs__tab--active' : ''}" data-tab="data">
                            按数据类型
                        </div>
                    </div>
                    <div class="history-page__filters">
                        <input type="date" class="input input--sm" id="filter-date-from" title="开始日期" style="width: 130px;">
                        <span style="color: var(--color-text-disabled);">-</span>
                        <input type="date" class="input input--sm" id="filter-date-to" title="结束日期" style="width: 130px;">
                        <input type="text" class="input input--sm" id="filter-keyword" placeholder="关键词搜索..." style="width: 140px;">
                        <button class="btn btn--ghost btn--sm" id="btn-filter-apply">筛选</button>
                    </div>
                    <div class="history-page__toolbar">
                        <button class="btn btn--secondary btn--sm" id="btn-send-to-beta" disabled>发送到 Beta</button>
                        <button class="btn btn--ghost btn--sm" id="btn-overlay-3d">叠加到 3D</button>
                    </div>
                    <div class="history-page__sessions" id="history-session-list">
                        <div style="color: var(--color-text-disabled); padding: var(--space-lg);">加载中...</div>
                    </div>
                </div>
                <div class="history-page__right" id="history-detail">
                    ${this._renderEmptyDetail()}
                </div>
            </div>
        `;

        this._bindEvents();
    }

    _renderEmptyDetail() {
        const empty = new EmptyState({
            icon: '📊',
            title: '选择历史记录',
            desc: '从左侧列表中选择一个任务查看详情和回放',
        });
        return empty.render().outerHTML;
    }

    _bindEvents() {
        // Sub-tabs
        const tabs = this.container?.querySelectorAll('#history-sub-tabs .tabs__tab');
        tabs?.forEach(tab => {
            tab.addEventListener('click', () => {
                this.activeSubTab = tab.dataset.tab;
                this.render();
                this._loadSessions();
            });
        });

        // Filter
        const filterBtn = this.container?.querySelector('#btn-filter-apply');
        filterBtn?.addEventListener('click', () => this._loadSessions());

        // Send to Beta
        const sendBtn = this.container?.querySelector('#btn-send-to-beta');
        sendBtn?.addEventListener('click', () => {
            const selected = Array.from(this.selectedSessions);
            bus.emit('chat-send', `请分析以下历史任务: ${selected.join(', ')}`);
        });

        // Overlay to 3D
        const overlayBtn = this.container?.querySelector('#btn-overlay-3d');
        overlayBtn?.addEventListener('click', () => {
            const session = store.get('history.selectedSession');
            if (session && session.trajectory) {
                sharedTrajectoryLine.setPlanned(session.trajectory);
                if (session.waypoints) sharedWaypointMarker.setWaypoints(session.waypoints);
                store.set('beta.fieldOverlay', true);
            }
        });
    }

    async _loadSessions() {
        try {
            const keyword = this.container?.querySelector('#filter-keyword')?.value || '';
            const dateFrom = this.container?.querySelector('#filter-date-from')?.value || '';
            const dateTo = this.container?.querySelector('#filter-date-to')?.value || '';

            const params = {};
            if (keyword) params.keyword = keyword;
            if (dateFrom) params.date_from = dateFrom;
            if (dateTo) params.date_to = dateTo;
            if (this.activeSubTab) params.type = this.activeSubTab;

            const result = await apiManager.getSessions(params);
            this.sessions = Array.isArray(result) ? result : (result?.sessions || result?.data || []);
        } catch (e) {
            console.warn('[HistoryPage] could not load sessions:', e.message);
            this.sessions = [];
        }

        const listEl = this.container?.querySelector('#history-session-list');
        if (!listEl) return;

        if (this.sessions.length === 0) {
            const empty = new EmptyState({
                icon: '📋',
                title: '无历史记录',
                desc: '尚未有完成的试飞任务',
            });
            listEl.innerHTML = '';
            listEl.appendChild(empty.render());
        } else {
            listEl.innerHTML = '';
            for (const session of this.sessions) {
                session.selected = this.selectedSessions.has(session.id);
                const card = new SessionCard(session, {
                    onClick: (s) => {
                        store.set('history.selectedSession', s);
                        this._renderDetail(s);
                    },
                    onSelect: (s, checked) => {
                        if (checked) {
                            this.selectedSessions.add(s.id);
                        } else {
                            this.selectedSessions.delete(s.id);
                        }
                        const sendBtn = this.container?.querySelector('#btn-send-to-beta');
                        if (sendBtn) sendBtn.disabled = this.selectedSessions.size === 0;
                    },
                });
                listEl.appendChild(card.render());
            }
        }
    }

    _renderDetail(session) {
        const detailArea = this.container?.querySelector('#history-detail');
        if (!detailArea) return;

        const dateStr = session.date || session.created_at
            ? new Date(session.date || session.created_at).toLocaleString('zh-CN')
            : '--';

        detailArea.innerHTML = `
            <div class="history-page__detail">
                <div class="history-page__detail-section">
                    <div class="history-page__detail-title">任务详情</div>
                    <div class="card card--raised" style="padding: var(--space-md);">
                        <div style="font-size: var(--font-lg); font-weight: 600; margin-bottom: var(--space-sm);">${session.task_title || session.name || '未知任务'}</div>
                        <div style="font-size: var(--font-sm); color: var(--color-text-secondary);">时间: ${dateStr}</div>
                        <div style="font-size: var(--font-sm); color: var(--color-text-secondary);">状态: ${session.status || '--'}</div>
                        <div style="font-size: var(--font-sm); color: var(--color-text-secondary); margin-top: var(--space-sm);">${session.task_summary || session.description || '无描述'}</div>
                    </div>
                </div>

                <div class="history-page__detail-section">
                    <div class="history-page__detail-title">回放控制</div>
                    <div id="timeline-control-container"></div>
                </div>

                <div class="history-page__detail-section" style="flex: 1; min-height: 250px;">
                    <div class="history-page__detail-title">轨迹回放</div>
                    <div id="history-chart-container" style="width: 100%; height: 300px; border: 1px solid var(--color-border); border-radius: var(--radius-md);"></div>
                </div>
            </div>
        `;

        // Timeline control
        const tlContainer = detailArea.querySelector('#timeline-control-container');
        if (tlContainer) {
            this.timelineControl = new TimelineControl(tlContainer);
            this.timelineControl.mount();
        }

        // History chart
        const chartContainer = detailArea.querySelector('#history-chart-container');
        if (chartContainer) {
            this.historyChartPanel = new ViewPanel(0, 'chart', 'history');
            this.historyChartPanel.mount(chartContainer);
        }
    }
}

export { HistoryPage };
