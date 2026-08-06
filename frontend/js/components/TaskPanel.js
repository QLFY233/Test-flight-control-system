/**
 * TaskPanel — 任务管理 (挂在 [ BETA AI ] 表头最右侧)。
 *
 * 任务 = flight session: 绑定 β/α 对话记录 (conversations 表) + 飞行数据 (telemetry 表)。
 * 功能: 新建任务 / 恢复任务 (切换当前会话并载入对话+飞行数据) / 重命名 / 删除记录。
 *
 * 结构说明:
 *  - 表头按钮: ChatPanel.render() 每次会整体重建 sidebar DOM, 故本组件监听
 *    bus 'chat-panel-rendered' 事件幂等重挂按钮 (已存在则跳过)。
 *  - 下拉面板: 挂到 document.body (fixed 定位, 锚定按钮位置) — chat-sidebar
 *    本身 overflow:hidden, 面板作为其子元素会被裁剪。
 */

import store from '../state.js';
import bus from '../event-bus.js';
import { apiManager } from '../shared.js';
import { esc } from '../escape.js';

// 遥测条数显示: >=1000 → 1.2k
function fmtCount(n) {
    if (n == null) return 0;
    if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k';
    return n;
}

class TaskPanel {
    constructor() {
        this._open = false;
        this._panel = null;
        this._tasks = [];
        this._loading = false;
        this._loadError = '';
        this._renamingId = null;
        this._confirmDeleteId = null;
        this._busyId = null;          // 恢复中的任务 id (行禁用 + 状态提示)
        this._boundOnRendered = this._attachToggle.bind(this);
        this._boundOnDocClick = this._onDocClick.bind(this);
        this._boundOnKey = this._onKey.bind(this);
        this._boundOnResize = this._position.bind(this);
        this._boundOnRestored = this._onTaskRestored.bind(this);
    }

    mount() {
        bus.on('chat-panel-rendered', this._boundOnRendered);
        bus.on('task-restored', this._boundOnRestored);
        this._attachToggle();
    }

    // ── 表头按钮 (最右侧) ──

    _attachToggle() {
        const header = document.querySelector('.chat-sidebar__header');
        if (!header || header.querySelector('.task-panel__toggle')) return;
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'task-panel__toggle';
        btn.title = '任务管理 — 新建/恢复/重命名/删除 (任务绑定 β/α 对话与飞行数据)';
        btn.innerHTML = '<span class="task-panel__toggle-icon">☰</span>任务';
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.toggle();
        });
        header.appendChild(btn);
    }

    toggle() {
        if (this._open) this.close();
        else this.open();
    }

    open() {
        if (this._open) return;
        this._open = true;
        this._ensurePanel();
        this._refreshList();
        document.addEventListener('click', this._boundOnDocClick);
        document.addEventListener('keydown', this._boundOnKey);
        window.addEventListener('resize', this._boundOnResize);
    }

    close() {
        if (!this._open) return;
        this._open = false;
        document.removeEventListener('click', this._boundOnDocClick);
        document.removeEventListener('keydown', this._boundOnKey);
        window.removeEventListener('resize', this._boundOnResize);
        if (this._panel) this._panel.remove();
        this._panel = null;
        this._renamingId = null;
        this._confirmDeleteId = null;
    }

    _onDocClick(e) {
        if (this._panel && this._panel.contains(e.target)) return;
        if (e.target.closest && e.target.closest('.task-panel__toggle')) return;
        // 行内操作(重命名/确认删除)同步重渲染后事件目标已脱离 DOM → 不关闭面板
        if (e.target.isConnected === false) return;
        this.close();
    }

    _onKey(e) {
        if (e.key === 'Escape') this.close();
    }

    // ── 面板 ──

    _ensurePanel() {
        if (this._panel && this._panel.isConnected) return;
        const panel = document.createElement('div');
        panel.className = 'task-panel';
        panel.innerHTML = `
            <div class="task-panel__header">
                <span class="task-panel__title">TASKS /// 任务管理</span>
                <button type="button" class="btn btn--primary btn--sm task-panel__new" title="新建任务（对话与飞行数据归属新任务）">+ 新建</button>
            </div>
            <div class="task-panel__list"></div>
            <div class="task-panel__footer">任务绑定 β/α 对话 · 飞行数据</div>
        `;
        panel.querySelector('.task-panel__new').addEventListener('click', (e) => {
            e.stopPropagation();
            this._createTask();
        });        document.body.appendChild(panel);
        this._panel = panel;
        this._position();
    }

    _position() {
        if (!this._panel) return;
        const btn = document.querySelector('.task-panel__toggle');
        const rect = btn ? btn.getBoundingClientRect() : { bottom: 64, right: 12 };
        const top = Math.min(rect.bottom + 8, window.innerHeight - 64);
        this._panel.style.top = top + 'px';
        this._panel.style.right = Math.max(8, Math.round(window.innerWidth - rect.right) + 4) + 'px';
        this._panel.style.maxHeight = `calc(100vh - ${top + 20}px)`;
    }

    // ── 任务列表 ──

    async _refreshList() {
        this._loading = true;
        this._loadError = '';
        this._renderList();
        try {
            const tasks = await apiManager.getTaskList(100);
            this._tasks = Array.isArray(tasks) ? tasks : [];
        } catch (e) {
            console.warn('[TaskPanel] load tasks failed:', e);
            this._loadError = e.message || '加载失败';
        }
        this._loading = false;
        this._renderList();
    }

    _renderList() {
        if (!this._panel) return;
        const listEl = this._panel.querySelector('.task-panel__list');
        if (!listEl) return;

        if (this._loadError && !this._tasks.length) {
            listEl.innerHTML = `<div class="task-panel__hint">⚠ 加载失败: ${esc(this._loadError)}</div>`;
            return;
        }
        if (this._loading && !this._tasks.length) {
            listEl.innerHTML = '<div class="task-panel__hint">加载中...</div>';
            return;
        }
        if (!this._tasks.length) {
            listEl.innerHTML = '<div class="task-panel__hint">— 无任务记录 —<br>点击 [+ 新建] 创建任务</div>';
            return;
        }

        const currentId = store.get('flight.sessionId');
        listEl.innerHTML = '';
        for (const t of this._tasks) {
            listEl.appendChild(this._renderRow(t, currentId));
        }
    }

    _renderRow(t, currentId) {
        const row = document.createElement('div');
        const isActive = t.id === currentId;
        const isBusy = this._busyId === t.id;
        row.className = 'task-panel__row'
            + (isActive ? ' task-panel__row--active' : '')
            + (isBusy ? ' task-panel__row--busy' : '');

        const name = t.task_description || ('任务 #' + t.id.slice(-10));
        const ts = t.last_active || t.created_at;
        const dateStr = ts ? new Date(ts).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '--';
        const status = t.status || 'idle';
        const meta = `${dateStr} · β ${t.conv_count ?? 0} 条 · 数据 ${fmtCount(t.telemetry_count ?? 0)} 条 · ${esc(status)}`;

        if (this._renamingId === t.id) {
            row.innerHTML = `
                <div class="task-panel__rename">
                    <input type="text" class="input input--sm task-panel__rename-input" value="${esc(name)}" maxlength="60" spellcheck="false">
                    <div class="task-panel__row-actions">
                        <button type="button" class="btn btn--primary btn--sm" data-rename-ok>✓ 保存</button>
                        <button type="button" class="btn btn--ghost btn--sm" data-rename-cancel>✕</button>
                    </div>
                </div>
                <div class="task-panel__meta">${meta}</div>
            `;
            const input = row.querySelector('.task-panel__rename-input');
            row.querySelector('[data-rename-ok]').addEventListener('click', (e) => { e.stopPropagation(); this._saveRename(t.id, input); });
            row.querySelector('[data-rename-cancel]').addEventListener('click', (e) => { e.stopPropagation(); this._renamingId = null; this._renderList(); });
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') this._saveRename(t.id, input);
                else if (e.key === 'Escape') { this._renamingId = null; this._renderList(); }
            });
            setTimeout(() => { input.focus(); input.select(); }, 0);
        } else if (this._confirmDeleteId === t.id) {
            row.innerHTML = `
                <div class="task-panel__name"><span class="task-panel__name-text">${esc(name)}</span></div>
                <div class="task-panel__confirm">⚠ 删除该任务的全部 β/α 对话与飞行数据记录？</div>
                <div class="task-panel__row-actions">
                    <button type="button" class="btn btn--danger btn--sm" data-del-ok>确认删除</button>
                    <button type="button" class="btn btn--ghost btn--sm" data-del-cancel>取消</button>
                </div>
            `;
            row.querySelector('[data-del-ok]').addEventListener('click', (e) => { e.stopPropagation(); this._doDelete(t.id); });
            row.querySelector('[data-del-cancel]').addEventListener('click', (e) => { e.stopPropagation(); this._confirmDeleteId = null; this._renderList(); });
        } else {
            row.innerHTML = `
                <div class="task-panel__name">
                    ${isActive ? '<span class="task-panel__badge">当前</span>' : ''}
                    <span class="task-panel__name-text" title="${esc(name)}">${esc(name)}</span>
                    <span class="task-panel__status task-panel__status--${esc(status)}">${esc(status)}</span>
                </div>
                <div class="task-panel__meta">${meta}</div>
                <div class="task-panel__row-actions">
                    <button type="button" class="btn btn--ghost btn--sm" data-act="${esc(t.id)}" ${isActive ? 'disabled' : ''} title="切换当前会话并载入其对话与飞行数据">恢复</button>
                    <button type="button" class="btn btn--ghost btn--sm" data-rename="${esc(t.id)}">重命名</button>
                    <button type="button" class="btn btn--ghost btn--sm task-panel__btn-danger" data-del="${esc(t.id)}">删除</button>
                </div>
            `;
            row.querySelector(`[data-act="${esc(t.id)}"]`).addEventListener('click', (e) => { e.stopPropagation(); this._restoreTask(t.id); });
            row.querySelector(`[data-rename="${esc(t.id)}"]`).addEventListener('click', (e) => { e.stopPropagation(); this._startRename(t.id); });
            row.querySelector(`[data-del="${esc(t.id)}"]`).addEventListener('click', (e) => { e.stopPropagation(); this._confirmDelete(t.id); });
        }
        return row;
    }

    // ── 新建任务 ──

    async _createTask() {
        const now = new Date();
        const pad = (n) => String(n).padStart(2, '0');
        const name = `任务 ${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}`;
        try {
            const res = await apiManager.createTask({ task_description: name });
            if (!res || !res.id) throw new Error('未返回任务 id');
            this._resetUiForNewTask(res.id, name);
            this._renamingId = null;
            this._confirmDeleteId = null;
            await this._refreshList();
            bus.emit('toast', { message: `已新建任务「${name}」`, level: 'success' });
        } catch (e) {
            console.warn('[TaskPanel] create task failed:', e);
            bus.emit('toast', { message: '新建任务失败: ' + e.message, level: 'error' });
        }
    }

    /** 新任务: 清空当前对话/轨迹/飞行上下文, 绑定新会话 id */
    _resetUiForNewTask(sessionId, name) {
        store.batch(() => {
            store.set('chatHistory', []);
            store.set('flight.sessionId', sessionId);
            store.set('flight.taskTitle', name);
            store.set('flight.taskDescription', name);
            store.set('flight.status', 'idle');
            store.set('flight.progress', 0);
            store.set('flight.currentAction', 0);
            store.set('flight.totalActions', 0);
            store.set('flight.currentActionCode', '');
            store.set('flight.currentActionParams', null);
            store.set('trajectory.flown', []);
            store.set('trajectory.planned', []);
            store.set('trajectory.actionSequence', []);
            store.set('trajectory.currentTarget', null);
            store.set('trajectory.pending', null);
        });
        window.__app?.chatPanel?.render?.();
    }

    // ── 恢复任务 (切换当前会话, 数据由 app.js 'task-restore' 加载) ──

    async _restoreTask(taskId) {
        if (this._busyId) return;
        this._busyId = taskId;
        this._renderList();
        try {
            await apiManager.activateTask(taskId);
            bus.emit('task-restore', taskId);
            bus.emit('toast', { message: '正在恢复任务...', level: 'info' });
        } catch (e) {
            console.warn('[TaskPanel] restore task failed:', e);
            bus.emit('toast', { message: '恢复任务失败: ' + e.message, level: 'error' });
        } finally {
            this._busyId = null;
        }
    }

    _onTaskRestored() {
        this._refreshList();
    }

    // ── 重命名 ──

    _startRename(taskId) {
        this._renamingId = taskId;
        this._confirmDeleteId = null;
        this._renderList();
    }

    async _saveRename(taskId, inputEl) {
        const name = inputEl.value.trim();
        if (!name) { this._renamingId = null; this._renderList(); return; }
        try {
            await apiManager.renameTask(taskId, name);
            if (store.get('flight.sessionId') === taskId) {
                store.set('flight.taskTitle', name);
                store.set('flight.taskDescription', name);
            }
            this._renamingId = null;
            await this._refreshList();
            bus.emit('toast', { message: '已重命名任务', level: 'success' });
        } catch (e) {
            console.warn('[TaskPanel] rename task failed:', e);
            bus.emit('toast', { message: '重命名失败: ' + e.message, level: 'error' });
        }
    }

    // ── 删除记录 ──

    _confirmDelete(taskId) {
        this._confirmDeleteId = taskId;
        this._renamingId = null;
        this._renderList();
    }

    async _doDelete(taskId) {
        try {
            const res = await apiManager.deleteTask(taskId);
            this._confirmDeleteId = null;
            if (res && res.was_active) {
                // 删除的是当前任务 (后端已清空 session_id) → 立即新建任务承接
                await this._createTask();
            } else {
                await this._refreshList();
                bus.emit('toast', { message: '已删除任务记录', level: 'success' });
            }
        } catch (e) {
            console.warn('[TaskPanel] delete task failed:', e);
            bus.emit('toast', { message: '删除任务失败: ' + e.message, level: 'error' });
        }
    }
}

export { TaskPanel };
