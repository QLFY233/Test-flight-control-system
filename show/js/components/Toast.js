/**
 * Toast — Global notification toast system.
 * Dispatched via event-bus 'toast' event.
 * Auto-dismiss after configurable duration.
 * Levels: success, error, warning, info.
 */

import bus from '../event-bus.js';

const TOAST_DURATION = 4000;
let container = null;

function ensureContainer() {
    if (container && document.body.contains(container)) return container;
    container = document.createElement('div');
    container.className = 'toast-container';
    container.style.cssText = 'position: fixed; top: 16px; right: 16px; z-index: 10000; display: flex; flex-direction: column; gap: 8px; pointer-events: none;';
    document.body.appendChild(container);
    return container;
}

function createToastEl(message, level = 'info', duration = TOAST_DURATION) {
    const colors = {
        success: '#4CAF50',
        error: '#F44336',
        warning: '#FFC107',
        info: '#2196F3',
    };
    const bgColors = {
        success: 'rgba(76,175,80,0.15)',
        error: 'rgba(244,67,54,0.15)',
        warning: 'rgba(255,193,7,0.15)',
        info: 'rgba(33,150,243,0.15)',
    };
    const el = document.createElement('div');
    el.className = `toast toast--${level}`;
    el.style.cssText = `
        pointer-events: auto;
        padding: 10px 16px;
        border-radius: 8px;
        background: ${bgColors[level] || bgColors.info};
        border: 1px solid ${colors[level] || colors.info};
        color: #E0E0E0;
        font-size: 13px;
        font-family: 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
        max-width: 360px;
        word-break: break-word;
        box-shadow: 0 4px 12px rgba(0,0,0,0.4);
        animation: toast-in 0.25s ease;
        cursor: pointer;
    `;
    el.textContent = message;

    // Dismiss on click
    el.addEventListener('click', () => dismiss(el));

    // Auto-dismiss
    const timer = setTimeout(() => dismiss(el), duration);
    el._timer = timer;

    // Dismiss on hover to pause? No, keep simple.
    return el;
}

function dismiss(el) {
    if (el._timer) clearTimeout(el._timer);
    el.style.opacity = '0';
    el.style.transform = 'translateX(100%)';
    el.style.transition = 'opacity 0.3s, transform 0.3s';
    setTimeout(() => {
        if (el.parentNode) el.parentNode.removeChild(el);
    }, 300);
}

/**
 * Initialize Toast — subscribe to event-bus 'toast' events.
 * Event payload: { message: string, level?: 'success'|'error'|'warning'|'info', duration?: number }
 */
export function initToast() {
    bus.on('toast', (payload) => {
        if (!payload || !payload.message) return;
        const c = ensureContainer();
        const el = createToastEl(payload.message, payload.level || 'info', payload.duration || TOAST_DURATION);
        c.appendChild(el);
    });

    // Inject keyframe animation
    if (!document.getElementById('toast-style')) {
        const style = document.createElement('style');
        style.id = 'toast-style';
        style.textContent = `
            @keyframes toast-in {
                from { opacity: 0; transform: translateX(40px); }
                to { opacity: 1; transform: translateX(0); }
            }
        `;
        document.head.appendChild(style);
    }
}

export default { initToast };
