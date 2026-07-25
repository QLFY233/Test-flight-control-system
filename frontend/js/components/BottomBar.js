/**
 * BottomBar — Task progress, current action text, ABORT button.
 */

import store from '../state.js';
import { apiManager } from '../shared.js';

class BottomBar {
    constructor(container) {
        this.container = container;
    }

    mount() {
        const flight = store.get('flight');
        const progress = flight.progress || 0;
        const currentActionIdx = flight.currentAction || 0;
        const currentActionCode = flight.currentActionCode || '';
        const actionLabel = currentActionCode
            ? `[${currentActionCode}] 动作 ${currentActionIdx}/${flight.totalActions || 0}`
            : (currentActionIdx > 0 ? `动作 ${currentActionIdx}/${flight.totalActions || 0}` : '待命');
        const status = flight.status || 'idle';

        const showAbort = status === 'running' || status === 'paused';

        this.container.innerHTML = `
            <span class="bottom-bar__label">PROGRESS</span>
            <div class="bottom-bar__progress">
                <div class="bottom-bar__progress-fill" style="width: ${progress}%"></div>
            </div>
            <span class="bottom-bar__value">${progress}%</span>
            <span class="bottom-bar__sep"></span>
            <span class="bottom-bar__label">ACTION</span>
            <span class="bottom-bar__action">${actionLabel}</span>
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
                    alert('没有活动中的试飞任务');
                    return;
                }
                if (!confirm('确定要紧急中断当前试飞任务吗？')) return;

                abortBtn.disabled = true;
                abortBtn.textContent = '中断中...';
                try {
                    await apiManager.abortSession(sessionId);
                    store.set('flight.status', 'aborted');
                } catch (e) {
                    alert('中断失败: ' + e.message);
                } finally {
                    abortBtn.disabled = false;
                    abortBtn.textContent = '紧急中断';
                }
            });
        }
    }
}

export { BottomBar };
