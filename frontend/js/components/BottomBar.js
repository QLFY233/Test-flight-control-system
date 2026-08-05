/**
 * BottomBar — Task progress, current action text, ABORT button.
 */

import store from '../state.js';
import { apiManager } from '../shared.js';
import bus from '../event-bus.js';
import { esc } from '../escape.js';

class BottomBar {
    constructor(container) {
        this.container = container;
    }

    mount() {
        // 注: 重渲染由 app.js scheduleBottomBar 驱动 (store.subscribe('flight'/'trajectory') → bb.mount())
        // 不要在此处自订阅 — 每次 mount 累积订阅会泄漏/重复渲染
        this._render();
    }

    _render() {
        const flight = store.get('flight') || {};
        const progress = flight.progress || 0;
        const currentActionIdx = flight.currentAction || 0;
        const currentActionCode = flight.currentActionCode || '';
        const totalActions = flight.totalActions || 0;
        const actionLabel = currentActionCode
            ? `[${currentActionCode}] 动作 ${currentActionIdx}/${totalActions}`
            : (currentActionIdx > 0 ? `动作 ${currentActionIdx}/${totalActions}` : '待命');
        const status = flight.status || 'idle';

        // 冻结枚举（shared/protocol.py schema_version=2）：idle/hovering/planned/executing/completed/aborted
        const showAbort = status === 'executing';

        this.container.innerHTML = `
            <span class="bottom-bar__label">PROGRESS</span>
            <div class="bottom-bar__progress">
                <div class="bottom-bar__progress-fill" style="width: ${progress}%"></div>
            </div>
            <span class="bottom-bar__value">${progress}%</span>
            <span class="bottom-bar__sep"></span>
            <span class="bottom-bar__label">ACTION</span>
            <span class="bottom-bar__action">${esc(actionLabel)}</span>
            ${showAbort ? `
                <span class="bottom-bar__sep"></span>
                <button class="btn btn--danger btn--sm" id="btn-abort">/// ABORT</button>
            ` : ''}
        `;

        const abortBtn = this.container.querySelector('#btn-abort');
        if (abortBtn) {
            abortBtn.addEventListener('click', async () => {
                const sessionId = store.get('flight.sessionId');
                if (!sessionId) {
                    bus.emit('toast', { message: '没有活动中的试飞任务', level: 'warning' });
                    return;
                }
                if (!confirm('确定要紧急中断当前试飞任务吗？')) return;

                abortBtn.disabled = true;
                abortBtn.textContent = '中断中...';
                try {
                    await apiManager.abortSession(sessionId);
                    store.set('flight.status', 'aborted');
                    bus.emit('toast', { message: '任务已紧急中断', level: 'success' });
                } catch (e) {
                    bus.emit('toast', { message: '中断失败: ' + e.message, level: 'error' });
                } finally {
                    abortBtn.disabled = false;
                    abortBtn.textContent = '紧急中断';
                }
            });
        }
    }
}

export { BottomBar };
