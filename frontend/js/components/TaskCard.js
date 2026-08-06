/**
 * TaskCard — 三处统一的任务卡片 (AI 任务面板 / 总览最近任务 / 历史记录)。
 *
 * 统一语义（同一实体 = flight_sessions 行）:
 *   - 名称   = task_description || '任务 #' + id 后 10 位
 *   - 状态   = 飞行状态枚举 → 中文标签 + 颜色 (idle 空闲 / hovering 悬停 /
 *              planned 已规划 / executing 执行中 / completed 已完成 / aborted 已中止)
 *   - 时间   = last_active || created_at 短格式 (MM-DD HH:mm)
 *   - meta   = β 对话 N 条 · 飞行数据 N 条 (与后端 list_sessions_with_stats 对齐)
 *   - 当前   = 红色「当前」徽标 (store.flight.sessionId 匹配时)
 *
 * 操作 (与 AI 任务面板一致): 恢复(非当前) / 重命名(行内编辑) / 删除(行内确认)。
 * 删除当前任务时自动新建任务承接 (公共逻辑, 三处共用)。
 *
 * 布局: 可选 checkbox (历史页多选) + 主区域 (名称/状态/meta/操作)。
 */

import store from '../state.js';
import bus from '../event-bus.js';
import { apiManager } from '../shared.js';
import { esc, escAttr } from '../escape.js';

// ── 统一展示语义 ──

const STATUS_LABELS = {
    idle: '空闲',
    hovering: '悬停',
    planned: '已规划',
    executing: '执行中',
    completed: '已完成',
    aborted: '已中止',
};

// 状态 → 色调 (与 .task-card__status--{tone} 对应)
const STATUS_TONE = {
    executing: 'green',
    completed: 'green',
    hovering: 'blue',
    planned: 'amber',
    aborted: 'red',
};

export function taskStatusInfo(status) {
    const s = String(status || 'idle').toLowerCase();
    return {
        label: STATUS_LABELS[s] || s,
        tone: STATUS_TONE[s] || 'muted',
    };
}

export function taskDisplayName(s) {
    if (s && s.task_description) return s.task_description;
    return '任务 #' + ((s && s.id) ? s.id.slice(-10) : '?');
}

export function taskTimeStr(s) {
    const ts = (s && (s.last_active || s.created_at)) || null;
    if (!ts) return '--';
    const d = new Date(ts);
    if (Number.isNaN(d.getTime())) return '--';
    const pad = (n) => String(n).padStart(2, '0');
    return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function fmtCount(n) {
    if (n == null) return 0;
    if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k';
    return n;
}

/** meta 行: 时间 · β 对话 N 条 · 数据 N 条 · 状态 */
export function taskMetaStr(s) {
    const info = taskStatusInfo(s && s.status);
    return `${taskTimeStr(s)} · β ${s && s.conv_count != null ? s.conv_count : 0} 条 · 数据 ${fmtCount(s && s.telemetry_count)} 条 · ${info.label}`;
}

// ── 公共任务操作 (三处共用) ──

/** 新任务名: 任务 MM-DD HH:mm */
function _newTaskName() {
    const now = new Date();
    const pad = (n) => String(n).padStart(2, '0');
    return `任务 ${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}`;
}

/** 切到新任务: 清空当前对话/轨迹/飞行上下文, 绑定新会话 id (ChatPanel 重渲染) */
export function resetUiForNewTask(sessionId, name) {
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

/** 新建任务 (后端切为当前会话)。成功返回 {id, name}, 失败抛错。 */
export async function createNewTask() {
    const name = _newTaskName();
    const res = await apiManager.createTask({ task_description: name });
    if (!res || !res.id) throw new Error('未返回任务 id');
    resetUiForNewTask(res.id, name);
    bus.emit('toast', { message: `已新建任务「${name}」`, level: 'success' });
    return { id: res.id, name };
}

/**
 * 删除任务记录 (级联删对话+飞行数据)。
 * 删除的是当前任务时 → 自动新建任务承接 (后端 session_id 已清空, 遥测流不中断)。
 */
export async function deleteTaskRecord(taskId) {
    const res = await apiManager.deleteTask(taskId);
    if (res && res.was_active) {
        await createNewTask();
    } else {
        bus.emit('toast', { message: '已删除任务记录', level: 'success' });
    }
    return res;
}

/** 恢复任务: 切换当前会话 + 通知 app.js 载入对话/轨迹数据 */
export async function activateTaskRecord(taskId) {
    await apiManager.activateTask(taskId);
    bus.emit('task-restore', taskId);
    bus.emit('toast', { message: '正在恢复任务...', level: 'info' });
}

// ── TaskCard 组件 ──

class TaskCard {
    /**
     * @param {object} session 后端 /api/sessions 行
     * @param {object} [opts]
     * @param {boolean} [opts.current] 是否当前任务 (显示当前徽标, 隐藏恢复)
     * @param {boolean} [opts.selectable] 显示多选 checkbox (历史页)
     * @param {boolean} [opts.selected]
     * @param {Function} [opts.onSelect] (session, checked)
     * @param {Function} [opts.onClick] (session) 卡片主体点击 (详情/跳转)
     * @param {Function} [opts.onChanged] () 重命名/删除/恢复后通知父级刷新列表
     */
    constructor(session, opts = {}) {
        this.session = session;
        this.opts = opts;
        this._renaming = false;
        this._deleting = false;
        this._busy = false;
        this._selected = !!opts.selected;
        this._el = null;
    }

    render() {
        const el = document.createElement('div');
        el.className = 'task-card'
            + (this.opts.current ? ' task-card--current' : '')
            + (this._selected ? ' task-card--selected' : '')
            + (this._busy ? ' task-card--busy' : '');
        this._el = el;

        const s = this.session;
        const info = taskStatusInfo(s.status);
        const name = taskDisplayName(s);

        if (this._renaming) {
            el.innerHTML = `
                <div class="task-card__main">
                    <div class="task-card__rename">
                        <input type="text" class="input input--sm task-card__rename-input" value="${escAttr(name)}" maxlength="60" spellcheck="false">
                        <button type="button" class="btn btn--primary btn--sm" data-rc-ok>✓ 保存</button>
                        <button type="button" class="btn btn--ghost btn--sm" data-rc-cancel>✕</button>
                    </div>
                    <div class="task-card__meta">${esc(taskMetaStr(s))}</div>
                </div>
            `;
            const input = el.querySelector('.task-card__rename-input');
            el.querySelector('[data-rc-ok]').addEventListener('click', (e) => { e.stopPropagation(); this._saveRename(input); });
            el.querySelector('[data-rc-cancel]').addEventListener('click', (e) => { e.stopPropagation(); this._renaming = false; this._rerender(); });
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') this._saveRename(input);
                else if (e.key === 'Escape') { this._renaming = false; this._rerender(); }
            });
            setTimeout(() => { input.focus(); input.select(); }, 0);
        } else if (this._deleting) {
            el.innerHTML = `
                <div class="task-card__main">
                    <div class="task-card__name"><span class="task-card__name-text">${esc(name)}</span></div>
                    <div class="task-card__confirm">⚠ 删除该任务的全部 β/α 对话与飞行数据记录？</div>
                    <div class="task-card__actions">
                        <button type="button" class="btn btn--danger btn--sm" data-rc-delok>确认删除</button>
                        <button type="button" class="btn btn--ghost btn--sm" data-rc-delcancel>取消</button>
                    </div>
                </div>
            `;
            el.querySelector('[data-rc-delok]').addEventListener('click', (e) => { e.stopPropagation(); this._doDelete(); });
            el.querySelector('[data-rc-delcancel]').addEventListener('click', (e) => { e.stopPropagation(); this._deleting = false; this._rerender(); });
        } else {
            el.innerHTML = `
                ${this.opts.selectable ? `<input type="checkbox" class="task-card__checkbox" ${this._selected ? 'checked' : ''}>` : ''}
                <div class="task-card__main">
                    <div class="task-card__name">
                        ${this.opts.current ? '<span class="task-card__badge">当前</span>' : ''}
                        <span class="task-card__name-text" title="${escAttr(name)}">${esc(name)}</span>
                        <span class="task-card__status task-card__status--${info.tone}">${esc(info.label)}</span>
                    </div>
                    <div class="task-card__meta">${esc(taskMetaStr(s))}</div>
                    <div class="task-card__actions">
                        ${this.opts.current ? '' : `<button type="button" class="btn btn--ghost btn--sm" data-rc-act>恢复</button>`}
                        <button type="button" class="btn btn--ghost btn--sm" data-rc-rename>重命名</button>
                        <button type="button" class="btn btn--ghost btn--sm task-card__btn-danger" data-rc-del>删除</button>
                    </div>
                </div>
            `;

            const checkbox = el.querySelector('.task-card__checkbox');
            if (checkbox) {
                checkbox.addEventListener('change', () => {
                    this._selected = checkbox.checked;
                    this.opts.onSelect && this.opts.onSelect(this.session, checkbox.checked);
                });
            }
            // 卡片主体点击 (排除按钮/checkbox) — 历史页详情/总览跳转
            el.addEventListener('click', (e) => {
                if (e.target.closest('button')) return;
                if (e.target.closest('.task-card__checkbox')) return;
                this.opts.onClick && this.opts.onClick(this.session);
            });
            el.querySelector('[data-rc-act]')?.addEventListener('click', (e) => { e.stopPropagation(); this._doActivate(); });
            el.querySelector('[data-rc-rename]').addEventListener('click', (e) => { e.stopPropagation(); this._renaming = true; this._rerender(); });
            el.querySelector('[data-rc-del]').addEventListener('click', (e) => { e.stopPropagation(); this._deleting = true; this._rerender(); });
        }

        return el;
    }

    _rerender() {
        if (!this._el) return;
        // ⚠ 必须先保存旧元素引用: render() 内部会把 this._el 覆盖为新元素,
        // 若此时再用 this._el 做 replaceChild 会抛 "node is not a child" 异常
        const old = this._el;
        const parent = old.parentNode;
        if (!parent) return;
        const next = this.render();
        parent.replaceChild(next, old);
    }

    async _doActivate() {
        if (this._busy) return;
        this._busy = true;
        this._rerender();
        try {
            await activateTaskRecord(this.session.id);
        } catch (e) {
            console.warn('[TaskCard] activate failed:', e);
            bus.emit('toast', { message: '恢复任务失败: ' + e.message, level: 'error' });
        } finally {
            this._busy = false;
            this._rerender();
        }
    }

    async _saveRename(inputEl) {
        const name = inputEl.value.trim();
        if (!name) { this._renaming = false; this._rerender(); return; }
        try {
            await apiManager.renameTask(this.session.id, name);
            this.session.task_description = name;   // 本地镜像同步
            if (store.get('flight.sessionId') === this.session.id) {
                store.set('flight.taskTitle', name);
                store.set('flight.taskDescription', name);
            }
            this._renaming = false;
            this._rerender();
            bus.emit('toast', { message: '已重命名任务', level: 'success' });
            this.opts.onChanged && this.opts.onChanged();
        } catch (e) {
            console.warn('[TaskCard] rename failed:', e);
            bus.emit('toast', { message: '重命名失败: ' + e.message, level: 'error' });
        }
    }

    async _doDelete() {
        try {
            await deleteTaskRecord(this.session.id);
            this.opts.onChanged && this.opts.onChanged();
        } catch (e) {
            console.warn('[TaskCard] delete failed:', e);
            bus.emit('toast', { message: '删除任务失败: ' + e.message, level: 'error' });
        }
    }
}

export { TaskCard };
