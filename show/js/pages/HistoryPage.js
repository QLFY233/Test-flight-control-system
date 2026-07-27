/**
 * HistoryPage — History browser with session list, filters, and playback.
 * Left: two sub-tabs (by flight / by data type), filters, session list with multi-select.
 * Right: task details (top) → FieldMap2D (middle) → playback controls (bottom).
 */

import store from '../state.js';
import bus from '../event-bus.js';
import { apiManager } from '../shared.js';
import { SessionCard } from '../components/SessionCard.js';
import { TimelineControl } from '../components/TimelineControl.js';
import { ViewPanel } from '../components/ViewPanel.js';
import { EmptyState } from '../components/EmptyState.js';

// Generate mock trajectory data for playback
function _generateMockTrajectory(durationSec, type) {
    const points = [];
    const n = Math.floor(durationSec * 10);
    const cx = 2.5, cy = 2.0;

    for (let i = 0; i < n; i++) {
        const t = i * 0.1;
        const frac = t / durationSec;
        let x, y, z;

        switch (type) {
        case 'square':
            // 矩形巡逻
            const seg = (frac * 4) % 1;
            const leg = Math.floor(frac * 4);
            if (leg === 0)      { x = 1 + seg * 3; y = 1; }
            else if (leg === 1) { x = 4; y = 1 + seg * 2; }
            else if (leg === 2) { x = 4 - seg * 3; y = 3; }
            else                { x = 1; y = 3 - seg * 2; }
            z = 1.0 + Math.sin(frac * Math.PI) * 0.3;
            break;

        case 'zigzag':
            // 之字形扫描
            x = 1 + frac * 3;
            y = 1 + Math.abs((frac * 12) % 2 - 1) * 2;
            z = 1.2;
            break;

        case 'spiral':
            // 螺旋展开
            const angle = frac * Math.PI * 4;
            const r = 0.5 + frac * 2;
            x = cx + Math.cos(angle) * r;
            y = cy + Math.sin(angle) * r;
            z = 0.8 + frac * 0.8;
            break;

        case 'figure8':
        default:
            // 8字航线
            const a = frac * Math.PI * 2;
            x = cx + Math.sin(a * 1.3) * 1.5 + frac * 0.5;
            y = cy + Math.sin(a) * Math.cos(a) * 1.2;
            z = 1.2 + Math.sin(a * 0.3) * 0.4;
            break;
        }

        points.push({
            x: Math.round(Math.max(0, Math.min(5, x)) * 100) / 100,
            y: Math.round(Math.max(0, Math.min(4, y)) * 100) / 100,
            z: Math.round(Math.max(0.1, Math.min(2.5, z)) * 100) / 100,
            t: t,
        });
    }
    return points;
}

class HistoryPage {
    constructor() {
        this.container = null;
        this.title = '历史';
        this.sessions = [];
        this.selectedSessions = new Set();
        this.activeSubTab = 'flight';
        this.timelineControl = null;
        this.fieldMapPanel = null;
        this._playbackInterval = null;
    }

    mount(container) {
        this.container = container;
        this.render();
        this._loadSessions();
    }

    unmount() {
        this._stopPlayback();
        this.timelineControl = null;
        if (this.fieldMapPanel) { this.fieldMapPanel.unmount(); this.fieldMapPanel = null; }
        // Clear trajectory so Beta page starts fresh
        store.batch(() => {
            store.set('trajectory.flown', []);
            store.set('trajectory.planned', []);
            store.set('history.playbackState', 'stopped');
        });
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
        this._setDefaultDates();
    }

    _setDefaultDates() {
        const pad = (n) => String(n).padStart(2, '0');
        const today = new Date();
        const todayStr = today.getFullYear() + '-' + pad(today.getMonth() + 1) + '-' + pad(today.getDate());
        const weekAgo = new Date(today.getTime() - 7 * 86400000);
        const weekAgoStr = weekAgo.getFullYear() + '-' + pad(weekAgo.getMonth() + 1) + '-' + pad(weekAgo.getDate());
        const fromEl = this.container?.querySelector('#filter-date-from');
        const toEl = this.container?.querySelector('#filter-date-to');
        if (fromEl && !fromEl.value) fromEl.value = weekAgoStr;
        if (toEl && !toEl.value) toEl.value = todayStr;
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
        const tabs = this.container?.querySelectorAll('#history-sub-tabs .tabs__tab');
        tabs?.forEach(tab => {
            tab.addEventListener('click', () => {
                this.activeSubTab = tab.dataset.tab;
                this.render();
                this._loadSessions();
            });
        });

        const filterBtn = this.container?.querySelector('#btn-filter-apply');
        filterBtn?.addEventListener('click', () => this._loadSessions());

        const sendBtn = this.container?.querySelector('#btn-send-to-beta');
        sendBtn?.addEventListener('click', () => {
            const selected = Array.from(this.selectedSessions);
            bus.emit('chat-send', `请分析以下历史任务: ${selected.join(', ')}`);
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
        this._stopPlayback();
        const detailArea = this.container?.querySelector('#history-detail');
        if (!detailArea) return;

        const dateStr = (() => {
            const d = session.date || session.created_at;
            if (!d) return '--';
            try { const dt = new Date(d); if (!isNaN(dt.getTime())) return dt.getFullYear() + '/' + String(dt.getMonth()+1).padStart(2,'0') + '/' + String(dt.getDate()).padStart(2,'0') + ' ' + String(dt.getHours()).padStart(2,'0') + ':' + String(dt.getMinutes()).padStart(2,'0'); } catch(e) {}
            return d;
        })();

        const title = session.task_title || session.name || '未知任务';
        const summary = session.task_summary || session.description || '无描述';
        const status = session.status || '--';

        // Generate mock trajectory data for this session
        const trajType = session.trajectory_type || 'figure8';
        const duration = session.duration || (this.activeSubTab === 'data' ? 30 : 46);
        const trajPoints = _generateMockTrajectory(duration, trajType);
        this._allTrajPoints = trajPoints;
        this._trajDuration = duration;
        this._abortAt = session.abort_at || 0;

        // Initialize store: empty flown, full planned as dashed preview, drone at start
        store.batch(() => {
            store.set('trajectory.flown', []);
            store.set('trajectory.planned', trajPoints);
            store.set('drone.position', { x: trajPoints[0].x, y: trajPoints[0].y, z: trajPoints[0].z });
            store.set('history.playbackState', 'stopped');
            store.set('history.playbackTime', 0);
            store.set('history.playbackSpeed', 1);
        });

        detailArea.innerHTML = `
            <div class="history-page__detail">
                <div class="history-page__detail-section">
                    <div class="history-page__detail-title">任务详情</div>
                    <div class="card card--raised" style="padding: var(--space-sm) var(--space-md);">
                        <div style="font-size: var(--font-md); font-weight: 600; margin-bottom: 4px;">${this._esc(title)}</div>
                        <div style="display: flex; gap: var(--space-lg); font-size: var(--font-xs); color: var(--color-text-secondary); flex-wrap: wrap;">
                            <span>时间: ${this._esc(dateStr)}</span>
                            <span>状态: ${this._esc(status)}</span>
                            <span>时长: ${duration}s</span>
                        </div>
                        <div style="font-size: var(--font-xs); color: var(--color-text-disabled); margin-top: 2px;">${this._esc(summary)}</div>
                    </div>
                </div>

                <div class="history-page__detail-section history-page__detail-section--grow">
                    <div class="history-page__detail-title">场地俯视图</div>
                    <div id="history-fieldmap-container" style="flex: 1; min-height: 300px; border: 1px solid var(--color-border);"></div>
                </div>

                <div class="history-page__detail-section">
                    <div class="history-page__detail-title">回放控制</div>
                    <div id="timeline-control-container" style="padding: var(--space-sm) 0;"></div>
                </div>
            </div>
        `;

        // FieldMap2D
        const fieldMapContainer = detailArea.querySelector('#history-fieldmap-container');
        if (fieldMapContainer) {
            if (this.fieldMapPanel) { this.fieldMapPanel.unmount(); }
            this.fieldMapPanel = new ViewPanel(0, 'chart', 'fieldmap');
            this.fieldMapPanel.mount(fieldMapContainer);
        }

        // Timeline control
        const tlContainer = detailArea.querySelector('#timeline-control-container');
        if (tlContainer) {
            const displayDuration = this._abortAt > 0 ? this._abortAt : duration;
            this.timelineControl = new TimelineControl(tlContainer, displayDuration);
            this.timelineControl.mount();

            // Hook into TimelineControl events after mount
            this._hookPlayback(tlContainer, trajPoints, duration);
        }
    }

    _hookPlayback(container, trajPoints, duration) {
        // Listen for play/pause
        const playBtn = container.querySelector('#tl-play-pause');
        if (playBtn) {
            const newBtn = playBtn.cloneNode(true);
            playBtn.parentNode.replaceChild(newBtn, playBtn);
            newBtn.addEventListener('click', () => {
                const state = store.get('history.playbackState');
                if (state === 'playing') {
                    this._stopPlayback();
                    store.set('history.playbackState', 'paused');
                    newBtn.innerHTML = '&#9654;';
                    newBtn.title = '播放';
                } else {
                    const maxT = this.timelineControl._getDuration ? this.timelineControl._getDuration() : duration;
                    this._startPlayback(trajPoints, maxT);
                    store.set('history.playbackState', 'playing');
                    newBtn.innerHTML = '&#9646;&#9646;';
                    newBtn.title = '暂停';
                }
            });
        }

        // Hook seek bar
        const seekBar = container.querySelector('#tl-seek');
        if (seekBar) {
            seekBar.addEventListener('input', () => {
                const t = parseFloat(seekBar.value);
                this._playbackTime = t;
                store.set('history.playbackTime', t);
                const flown = this._allTrajPoints.filter(pt => pt.t <= t);
                if (flown.length) {
                    const last = flown[flown.length - 1];
                    store.batch(() => {
                        store.set('drone.position', { x: last.x, y: last.y, z: last.z });
                        store.set('trajectory.flown', flown);
                    });
                }
                this._updateTimeDisplay(container);
            });
        }

        // Hook speed selector
        const speedSel = container.querySelector('#tl-speed');
        if (speedSel) {
            speedSel.addEventListener('change', () => {
                store.set('history.playbackSpeed', parseFloat(speedSel.value));
            });
        }

        // Hook step buttons
        container.querySelector('#tl-step-back')?.addEventListener('click', () => {
            let t = Math.max(0, (store.get('history.playbackTime') || 0) - 2);
            this._playbackTime = t;
            store.set('history.playbackTime', t);
            const pts = this._allTrajPoints;
            const flown = pts.filter(pt => pt.t <= t);
            if (flown.length) {
                const last = flown[flown.length - 1];
                store.batch(() => {
                    store.set('drone.position', { x: last.x, y: last.y, z: last.z });
                    store.set('trajectory.flown', flown);
                });
            }
            this._updateTimeDisplay(container);
            this._updateSeekBarVal(container);
        });
        container.querySelector('#tl-step-fwd')?.addEventListener('click', () => {
            const maxT = this.timelineControl._getDuration ? this.timelineControl._getDuration() : duration;
            let t = Math.min(maxT, (store.get('history.playbackTime') || 0) + 2);
            this._playbackTime = t;
            store.set('history.playbackTime', t);
            const pts = this._allTrajPoints;
            const flown = pts.filter(pt => pt.t <= t);
            if (flown.length) {
                const last = flown[flown.length - 1];
                store.batch(() => {
                    store.set('drone.position', { x: last.x, y: last.y, z: last.z });
                    store.set('trajectory.flown', flown);
                });
            }
            this._updateTimeDisplay(container);
            this._updateSeekBarVal(container);
        });
    }

    _startPlayback(trajPoints, maxT) {
        this._stopPlayback();
        this._playbackTime = store.get('history.playbackTime') || 0;
        const abortAt = this._abortAt;
        const effectiveMax = abortAt > 0 ? abortAt : maxT;
        const container = this.container?.querySelector('#timeline-control-container');
        this._playbackInterval = setInterval(() => {
            this._playbackTime += 0.15 * (store.get('history.playbackSpeed') || 1);
            if (this._playbackTime >= effectiveMax) {
                this._playbackTime = effectiveMax;
                store.set('history.playbackTime', this._playbackTime);
                store.set('history.playbackState', 'paused');
                this._stopPlayback();
                if (container) {
                    const btn = container.querySelector('#tl-play-pause');
                    if (btn) { btn.innerHTML = '&#9654;'; btn.title = '播放'; }
                }
            }
            const t = this._playbackTime;
            store.set('history.playbackTime', t);
            const flown = trajPoints.filter(pt => pt.t <= t);
            if (flown.length) {
                const last = flown[flown.length - 1];
                store.batch(() => {
                    store.set('drone.position', { x: last.x, y: last.y, z: last.z });
                    store.set('drone.timestamp', Date.now());
                    store.set('trajectory.flown', flown);
                });
            }
            if (container) {
                this._updateTimeDisplay(container);
                this._updateSeekBarVal(container);
            }
        }, 150);
    }

    _stopPlayback() {
        if (this._playbackInterval) {
            clearInterval(this._playbackInterval);
            this._playbackInterval = null;
        }
    }

    _updateTimeDisplay(container) {
        const t = store.get('history.playbackTime') || 0;
        const maxT = this.timelineControl._getDuration ? this.timelineControl._getDuration() : 60;
        const span = container.querySelector('.timeline-control span');
        if (span) {
            const fmt = (s) => { const m = Math.floor(s/60), sc = Math.floor(s%60); return String(m).padStart(2,'0')+':'+String(sc).padStart(2,'0'); };
            span.textContent = fmt(t) + ' / ' + fmt(maxT);
        }
    }

    _updateSeekBarVal(container) {
        const seekBar = container.querySelector('#tl-seek');
        const t = store.get('history.playbackTime') || 0;
        if (seekBar) seekBar.value = t;
    }

    _esc(text) {
        const div = document.createElement('div');
        div.textContent = String(text || '');
        return div.innerHTML;
    }
}

export { HistoryPage };
