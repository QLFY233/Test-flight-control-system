/**
 * HistoryPage — History browser with session list, filters, and playback.
 * Left: two sub-tabs (by flight / by data type), filters, session list with multi-select.
 * Right: selected session detail + analysis summary + TimelineControl + playback chart.
 */

import store from '../state.js';
import bus from '../event-bus.js';
import { apiManager } from '../shared.js';
import { TaskCard, taskDisplayName, taskStatusInfo, taskMetaStr } from '../components/TaskCard.js';
import { TimelineControl } from '../components/TimelineControl.js';
import { EmptyState } from '../components/EmptyState.js';
import { HistoryPanels } from '../history/HistoryPanels.js';
import { FieldMap2D } from '../charts/FieldMap2D.js';
import { Scene3D } from '../charts/Scene3D.js';
import { playbackEngine } from '../history/playback.js';
import { esc } from '../escape.js';

class HistoryPage {
    constructor() {
        this.container = null;
        this.title = '历史';
        this.sessions = [];
        this.selectedSessions = new Set();
        this.activeSubTab = 'flight'; // 'flight' | 'data'
        this.timelineControl = null;
        this.historyMap2D = null;    // 2D 场地俯视图 (历史模式)
        this.historyScene3D = null;  // 3D 视图 (历史模式)
        this.historyPanels = null;
        this._boundOnTaskRestored = null;
    }

    mount(container) {
        this.container = container;
        this.render();
        this._loadSessions();
        // 回放引擎: 订阅播放/seek/步进/倍速事件, rAF 推进 (页面内常驻)
        playbackEngine.mount();
        // 任务恢复/重命名/删除后刷新列表 (当前徽标/名称同步)
        this._boundOnTaskRestored = () => this._loadSessions();
        bus.on('task-restored', this._boundOnTaskRestored);
    }

    unmount() {
        if (this._boundOnTaskRestored) { bus.off('task-restored', this._boundOnTaskRestored); this._boundOnTaskRestored = null; }
        playbackEngine.unmount();
        this._disposeDetailInstances();
        this.container = null;
    }

    /** 清理详情区实例 (页面卸载 + 会话切换时复用, 防订阅/echarts/three 泄漏)。 */
    _disposeDetailInstances() {
        if (this.timelineControl) { this.timelineControl.unmount?.(); this.timelineControl = null; }
        if (this.historyPanels) { this.historyPanels.unmount(); this.historyPanels = null; }
        if (this.historyMap2D) { this.historyMap2D.unmount(); this.historyMap2D = null; }
        if (this.historyScene3D) { this.historyScene3D.unmount(); this.historyScene3D = null; }
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
            const currentId = store.get('flight.sessionId');
            for (const session of this.sessions) {
                // 统一任务卡片 (与 AI 任务面板/总览一致): 多选 + 详情 + 恢复/重命名/删除
                const card = new TaskCard(session, {
                    selectable: true,
                    selected: this.selectedSessions.has(session.id),
                    current: session.id === currentId,
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
                    onChanged: () => this._loadSessions(),
                });
                listEl.appendChild(card.render());
            }
        }
    }

    /**
     * C1: 加载选中会话的回放数据集 → store.history.playback.dataset。
     * 数据源: GET /api/history/telemetry/{sid} (t/pos/vel/accel/angular_vel/quat) +
     *         GET /api/sessions/{sid} (task_description/alpha_actions/status)。
     * 独立存储路径, 与实时 trajectory.flown 隔离; 失败静默 (面板显示空态)。
     */
    async _loadPlaybackDataset(session) {
        const sid = session?.id;
        if (!sid) return 0;
        // 先清空旧会话数据, 防加载期间面板闪现上一会话内容
        store.set('history.playback.dataset', null);
        // 遥测 + 会话详情并行拉取 (缩短选中→渲染延迟)
        const [res, detail] = await Promise.all([
            apiManager.getTelemetry(sid, { limit: 10000 }).catch((e) => {
                console.warn('[HistoryPage] telemetry load failed:', e);
                return { data: [] };
            }),
            apiManager.getSessionDetail(sid).catch(() => null),
        ]);
        let raw = (res && Array.isArray(res.data)) ? res.data : [];

        // 遥测 → 回放点 (定长数值, 兼容端点已做 NULL→0)
        const points = raw.map(r => ({
            t: r.t ?? 0,
            x: r.pos?.[0] ?? 0, y: r.pos?.[1] ?? 0, z: r.pos?.[2] ?? 0,
            vx: r.vel?.[0] ?? 0, vy: r.vel?.[1] ?? 0, vz: r.vel?.[2] ?? 0,
            ax: r.accel?.[0] ?? 0, ay: r.accel?.[1] ?? 0, az: r.accel?.[2] ?? 0,
            wx: r.angular_vel?.[0] ?? 0, wy: r.angular_vel?.[1] ?? 0, wz: r.angular_vel?.[2] ?? 0,
        }));

        // alpha_actions (ActionCommand JSON) → 目标点序列 + 动作数 (任务进度面板用)
        let planned = [];
        let totalActions = 0;
        if (detail && typeof detail.alpha_actions === 'string' && detail.alpha_actions.trim()) {
            try {
                const cmd = JSON.parse(detail.alpha_actions);
                totalActions = Array.isArray(cmd?.actions) ? cmd.actions.length : 0;
                planned = (cmd.actions || []).map(a => {
                    const tgt = a?.target;
                    if (Array.isArray(tgt) && tgt.length >= 3) {
                        return { x: tgt[0], y: tgt[1], z: tgt[2] };
                    }
                    return null;
                }).filter(Boolean);
            } catch (e) { /* 解析失败忽略 */ }
        }

        const tStart = points.length ? points[0].t : 0;
        const tEnd = points.length ? points[points.length - 1].t : 0;

        // 提交前守卫: 期间用户已切到别的会话 → 丢弃本次结果 (防慢响应竞态覆盖新选择)
        if (store.get('history.selectedSession')?.id !== sid) return 0;

        store.set('history.playback.dataset', {
            sessionId: sid,
            points,
            tStart,
            tEnd,
            duration: Math.max(tEnd - tStart, 0),
            taskInfo: {
                name: taskDisplayName(session),
                status: session.status || (detail?.status ?? 'idle'),
                totalActions,
                convCount: session.conv_count ?? 0,
                telemetryCount: points.length,
            },
            planned,
        });
        store.set('history.playback.index', 0);
        store.set('history.playbackTime', 0);
        store.set('history.playbackState', 'stopped');
        return points.length;
    }

    _renderDetail(session) {
        const detailArea = this.container?.querySelector('#history-detail');
        if (!detailArea) return;

        // 清理上一会话的详情实例 (防重复 select 泄漏订阅/echarts)
        this._disposeDetailInstances();

        // C1: 异步加载选中会话的回放数据集 (独立路径 store.history.playback.dataset, 不污染实时轨迹)
        this._loadPlaybackDataset(session);

        // 统一任务语义 (与 AI 任务面板/总览一致)
        const name = taskDisplayName(session);
        const info = taskStatusInfo(session.status);
        const ts = session.last_active || session.created_at;
        const dateStr = ts ? new Date(ts).toLocaleString('zh-CN') : '--';
        const summary = session.task_description || '— 无任务描述 —';

        detailArea.innerHTML = `
            <div class="history-page__detail">
                <div class="history-page__detail-section">
                    <div class="history-page__detail-title">任务详情</div>
                    <div class="card card--raised" style="padding: var(--space-md);">
                        <div style="font-size: var(--font-lg); font-weight: 600; margin-bottom: var(--space-sm);">${esc(name)} <span class="task-card__status task-card__status--${info.tone}">${esc(info.label)}</span></div>
                        <div style="font-size: var(--font-sm); color: var(--color-text-secondary);">时间: ${esc(dateStr)}</div>
                        <div style="font-size: var(--font-sm); color: var(--color-text-secondary);">会话: ${esc(session.id || '--')}</div>
                        <div style="font-size: var(--font-sm); color: var(--color-text-secondary); margin-top: var(--space-sm);">${esc(summary)}</div>
                        <div style="font-size: var(--font-sm); color: var(--color-text-secondary); margin-top: var(--space-sm);">β 对话 ${session.conv_count ?? 0} 条 · 飞行数据 ${session.telemetry_count ?? 0} 条</div>
                    </div>
                </div>

                <div class="history-page__detail-section">
                    <div class="history-page__detail-title">回放控制</div>
                    <div id="timeline-control-container"></div>
                </div>

                <div class="history-page__detail-section" style="flex:1;min-height:420px;min-width:0;">
                    <div style="display:flex;gap:var(--space-3);height:100%;min-height:0;flex-wrap:wrap;">
                        <!-- 左: 看板数据 (统计 + 任务摘要, 值型非坐标图) -->
                        <div style="flex:0 0 340px;min-width:280px;display:flex;flex-direction:column;gap:var(--space-3);min-height:0;">
                            <div class="history-page__detail-title">看板数据</div>
                            <div id="history-panels-container" style="flex:1;overflow-y:auto;"></div>
                        </div>
                        <!-- 右: 轨迹 (2D 场地俯视 + 3D) -->
                        <div style="flex:1;min-width:420px;display:flex;flex-direction:column;gap:var(--space-3);min-height:0;">
                            <div class="history-page__detail-title">轨迹回放 · 场地俯视 + 3D</div>
                            <div style="flex:1;min-height:0;display:flex;gap:var(--space-3);flex-wrap:wrap;">
                                <div id="history-map-2d" style="flex:1;min-width:240px;height:320px;border:1px solid var(--color-border);border-radius:var(--radius-md);"></div>
                                <div id="history-scene-3d" style="flex:1;min-width:240px;height:320px;border:1px solid var(--color-border);border-radius:var(--radius-md);"></div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;

        // Timeline control
        const tlContainer = detailArea.querySelector('#timeline-control-container');
        if (tlContainer) {
            this.timelineControl = new TimelineControl(tlContainer);
            this.timelineControl.mount();
        }

        // 数据面板 (C3: 高度/速度/加速度/角速度 + 统计 + 任务摘要)
        const panelsContainer = detailArea.querySelector('#history-panels-container');
        if (panelsContainer) {
            this.historyPanels = new HistoryPanels();
            this.historyPanels.mount(panelsContainer);
        }

        // 轨迹: 2D 场地俯视图 + 3D 视图 (历史模式, 数据匹配选中任务)
        const mapContainer = detailArea.querySelector('#history-map-2d');
        if (mapContainer) {
            this.historyMap2D = new FieldMap2D('history');
            this.historyMap2D.mount(mapContainer);
        }
        const sceneContainer = detailArea.querySelector('#history-scene-3d');
        if (sceneContainer) {
            this.historyScene3D = new Scene3D('history');
            this.historyScene3D.mount(sceneContainer);
        }
    }
}

export { HistoryPage };
