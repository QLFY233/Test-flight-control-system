/**
 * FloatingBall — Fixed floating action button with fan menu.
 * Positioned to the LEFT of the chat sidebar.
 * Shortcuts stored in localStorage.
 */
import bus from '../event-bus.js';

const DEFAULT_SHORTCUTS = [
    { id: 'sc-1', icon: '⬆', name: '上升 0.5m', actions: [{ type: 'chat_message', text: '上升 0.5 米' }] },
    { id: 'sc-2', icon: '⬇', name: '下降 0.5m', actions: [{ type: 'chat_message', text: '下降 0.5 米' }] },
    { id: 'sc-3', icon: '⏸', name: '悬停', actions: [{ type: 'chat_message', text: '悬停' }] },
    { id: 'sc-4', icon: '🏠', name: '回到原点', actions: [{ type: 'chat_message', text: '回到起飞点' }] },
    { id: 'sc-5', icon: '📊', name: '查看高度', actions: [{ type: 'chat_message', text: '显示高度趋势' }] },
    { id: 'sc-6', icon: '💬', name: '状态查询', actions: [{ type: 'chat_message', text: '当前状态如何？' }] },
];

class FloatingBall {
    constructor(container) {
        this.container = container;
        this.expanded = false;
        this.shortcuts = this._loadShortcuts();
        this._dragState = null;
        this._boundOutsideClick = this._handleOutsideClick.bind(this);
    }

    mount() {
        this.render();
    }

    render() {
        // Position to left of chat sidebar (340px sidebar + 20px gap)
        this.container.style.cssText = 'position:fixed;right:370px;bottom:100px;z-index:var(--z-sticky);';

        this.container.innerHTML = `
            <div class="floating-ball" id="floating-ball-main">
                <span class="floating-ball__icon">${this.expanded ? '✕' : '⚙'}</span>
            </div>
        `;

        const ball = this.container.querySelector('#floating-ball-main');
        if (!ball) return;

        ball.addEventListener('click', (e) => {
            e.stopPropagation();
            if (this.expanded) this._collapse();
            else this._expand();
        });

        // Long press (600ms) for edit mode
        let longPressTimer = null;
        ball.addEventListener('pointerdown', (e) => {
            longPressTimer = setTimeout(() => {
                this._enterEditMode();
            }, 600);
        });
        ball.addEventListener('pointerup', () => clearTimeout(longPressTimer));
        ball.addEventListener('pointermove', () => clearTimeout(longPressTimer));
    }

    _expand() {
        this.expanded = true;
        this.render();

        const ball = this.container.querySelector('#floating-ball-main');
        if (!ball) return;

        const ballRect = ball.getBoundingClientRect();
        const cx = ballRect.left + ballRect.width / 2;
        const cy = ballRect.top + ballRect.height / 2;
        const items = this.shortcuts;

        // Position fan items in an arc to the LEFT of the ball
        const angleStep = Math.PI / Math.max(items.length, 1);
        const startAngle = Math.PI - angleStep * (items.length - 1) / 2;

        items.forEach((item, i) => {
            const angle = startAngle + angleStep * i;
            const radius = 90;
            const tx = cx - Math.cos(angle) * radius - 22;
            const ty = cy - Math.sin(angle) * radius - 22;

            const el = document.createElement('div');
            el.className = 'fan-menu__item';
            el.style.cssText = `position:fixed;left:${tx}px;top:${ty}px;`;
            el.dataset.fanItem = item.id;
            el.innerHTML = `<span class="fan-menu__item-icon">${item.icon}</span>`;

            el.addEventListener('click', (ev) => {
                ev.stopPropagation();
                this._triggerShortcut(item);
                this._collapse();
            });
            document.body.appendChild(el);
        });

        // Click outside to close
        setTimeout(() => document.addEventListener('click', this._boundOutsideClick), 0);
    }

    _collapse() {
        this.expanded = false;
        document.querySelectorAll('[data-fan-item]').forEach(el => el.remove());
        document.removeEventListener('click', this._boundOutsideClick);
        this.render();
    }

    _handleOutsideClick(e) {
        if (e.target.closest('.floating-ball')) return;
        if (e.target.closest('[data-fan-item]')) return;
        this._collapse();
    }

    _triggerShortcut(shortcut) {
        const actions = shortcut.actions || [];
        if (!actions.length) return;

        let cancelled = false;
        const onEsc = (e) => { if (e.key === 'Escape') { cancelled = true; document.removeEventListener('keydown', onEsc); } };
        document.addEventListener('keydown', onEsc);
        setTimeout(() => document.removeEventListener('keydown', onEsc), 200);

        const run = (idx) => {
            if (cancelled || idx >= actions.length) return;
            const a = actions[idx];
            switch (a.type) {
                case 'chat_message': bus.emit('chat-send', a.text); run(idx + 1); break;
                case 'delay': setTimeout(() => run(idx + 1), a.ms || 1000); break;
                case 'chart': bus.emit('view-source-changed', { slot: 0, source: 'chart', chartType: a.chart }); run(idx + 1); break;
                default: run(idx + 1);
            }
        };
        run(0);
    }

    _enterEditMode() {
        bus.emit('open-shortcut-editor');
    }

    _loadShortcuts() {
        try {
            const saved = JSON.parse(localStorage.getItem('floating-ball-shortcuts'));
            if (Array.isArray(saved) && saved.length) return saved.map(s => s.actions ? s : { ...s, actions: s.action ? [s.action] : [] });
        } catch {}
        return DEFAULT_SHORTCUTS;
    }
}

export { FloatingBall };
