/**
 * TaskPanel — 任务管理 (挂在 [ BETA AI ] 表头最右侧)。
 *
 * 任务 = flight session: 绑定 β/α 对话记录 (conversations 表) + 飞行数据 (telemetry 表)。
 * 功能: 新建任务 / 恢复任务 / 重命名 / 删除记录。
 * 行渲染与操作全部复用 TaskCard (与 总览最近任务 / 历史记录 三处统一)。
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
import { TaskCard, createNewTask } from './TaskCard.js';

class TaskPanel {
    constructor() {
        this._open = false;
        this._panel = null;
        this._tasks = [];
        this._loading = false;
        this._loadError = '';
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
    }

    _onDocClick(e) {
        if (this._panel && this._panel.contains(e.target)) return;
        if (e.target.closest && e.target.closest('.task-panel__toggle')) return;
        // 行内操作(重命名/删除确认)同步重渲染后事件目标已脱离 DOM → 不关闭面板
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
        });
        document.body.appendChild(panel);
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

    // ── 任务列表 (行 = TaskCard, 与总览/历史统一) ──

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
            const card = new TaskCard(t, {
                current: t.id === currentId,
                onChanged: () => this._refreshList(),
            });
            listEl.appendChild(card.render());
        }
    }

    _onTaskRestored() {
        // 恢复完成: 刷新列表 (当前徽标/状态同步)
        this._refreshList();
    }

    // ── 新建任务 (公共逻辑在 TaskCard) ──

    async _createTask() {
        try {
            await createNewTask();
            await this._refreshList();
        } catch (e) {
            console.warn('[TaskPanel] create task failed:', e);
            bus.emit('toast', { message: '新建任务失败: ' + e.message, level: 'error' });
        }
    }
}

export { TaskPanel };
