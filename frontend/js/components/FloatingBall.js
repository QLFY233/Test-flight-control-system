/**
 * FloatingBall — Fixed floating action button with fan menu and drag support.
 * Click: expand fan menu (4-6 shortcuts)
 * Long press: edit mode
 * Drag: reposition along right edge
 * Shortcuts are stored in localStorage.
 */

import bus from '../event-bus.js';

const DEFAULT_SHORTCUTS = [
    { id: 'sc-1', icon: '⬆', name: '上升 0.5m', actions: [{ type: 'chat_message', text: '上升 0.5 米' }] },
    { id: 'sc-2', icon: '⬇', name: '下降 0.5m', actions: [{ type: 'chat_message', text: '下降 0.5 米' }] },
    { id: 'sc-3', icon: '⏸', name: '悬停', actions: [{ type: 'chat_message', text: '悬停' }] },
    { id: 'sc-4', icon: '\u{1F3E0}', name: '回到原点', actions: [{ type: 'chat_message', text: '回到起飞点' }] },
    { id: 'sc-5', icon: '\u{1F4CA}', name: '查看高度', actions: [{ type: 'chat_message', text: '显示高度趋势' }] },
    { id: 'sc-6', icon: '\u{1F4AC}', name: '状态查询', actions: [{ type: 'chat_message', text: '当前状态如何？' }] },
];

class FloatingBall {
    constructor(container) {
        this.container = container;
        this.expanded = false;
        this.editMode = false;
        this.shortcuts = this._loadShortcuts();
        this.dragging = false;
        this.dragStartY = 0;
        this.dragStartTop = 0;
        this._boundHandleClose = this._handleOutsideClick.bind(this);
    }

    mount() {
        this.render();
        this._positionDefault();
    }

    render() {
        this.container.innerHTML = `
            <div class="floating-ball" id="floating-ball-main" title="快捷操作">
                <span class="floating-ball__icon">${this.expanded ? '✕' : '⚙'}</span>
            </div>
        `;

        const ball = this.container.querySelector('#floating-ball-main');
        if (!ball) return;

        // Click handler
        ball.addEventListener('click', (e) => {
            if (this.dragging) return;
            e.stopPropagation();
            if (this.expanded) {
                this._collapse();
            } else {
                this._expand();
            }
        });

        // Long press (800ms) for edit mode
        let longPressTimer;
        ball.addEventListener('mousedown', (e) => {
            longPressTimer = setTimeout(() => {
                this._enterEditMode();
            }, 800);
        });
        ball.addEventListener('mouseup', () => clearTimeout(longPressTimer));
        ball.addEventListener('mouseleave', () => clearTimeout(longPressTimer));
        ball.addEventListener('touchstart', (e) => {
            longPressTimer = setTimeout(() => {
                this._enterEditMode();
            }, 800);
        });
        ball.addEventListener('touchend', () => clearTimeout(longPressTimer));

        // Drag
        ball.addEventListener('mousedown', (e) => {
            if (this.expanded) return;
            this.dragging = true;
            this.dragStartY = e.clientY;
            const top = parseInt(ball.style.top) || 0;
            this.dragStartTop = top;

            const onMove = (ev) => {
                const dy = ev.clientY - this.dragStartY;
                const newTop = Math.max(80, Math.min(window.innerHeight - 200, this.dragStartTop + dy));
                ball.style.top = newTop + 'px';
            };
            const onUp = () => {
                this.dragging = false;
                document.removeEventListener('mousemove', onMove);
                document.removeEventListener('mouseup', onUp);
            };
            document.addEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onUp);
        });

        // Touch drag
        ball.addEventListener('touchstart', (e) => {
            if (this.expanded) return;
            if (e.touches.length !== 1) return;
            this.dragging = true;
            this.dragStartY = e.touches[0].clientY;
            const top = parseInt(ball.style.top) || 0;
            this.dragStartTop = top;

            const onMove = (ev) => {
                const dy = ev.touches[0].clientY - this.dragStartY;
                const newTop = Math.max(80, Math.min(window.innerHeight - 200, this.dragStartTop + dy));
                ball.style.top = newTop + 'px';
            };
            const onUp = () => {
                this.dragging = false;
                document.removeEventListener('touchmove', onMove);
                document.removeEventListener('touchend', onUp);
            };
            document.addEventListener('touchmove', onMove);
            document.addEventListener('touchend', onUp);
        });
    }

    _expand() {
        this.expanded = true;
        this.render();

        // Create fan menu items
        const ball = this.container.querySelector('#floating-ball-main');
        if (!ball) return;

        const ballRect = ball.getBoundingClientRect();
        const cx = ballRect.left + ballRect.width / 2;
        const cy = ballRect.top + ballRect.height / 2;
        const radius = 80;
        const items = this.shortcuts;

        const fanContainer = document.createElement('div');
        fanContainer.className = 'fan-menu';
        fanContainer.style.left = '0px';
        fanContainer.style.top = '0px';
        fanContainer.style.width = '100vw';
        fanContainer.style.height = '100vh';
        fanContainer.id = 'fan-menu-container';

        const angleStep = Math.PI / (items.length + 1);
        const startAngle = Math.PI / 2 - (angleStep * (items.length - 1)) / 2;

        items.forEach((item, i) => {
            const angle = startAngle + angleStep * i;
            const tx = cx - Math.cos(angle) * radius;
            const ty = cy - Math.sin(angle) * radius;

            const itemEl = document.createElement('div');
            itemEl.className = 'fan-menu__item';
            itemEl.style.position = 'absolute';
            itemEl.style.left = (tx - 22) + 'px';
            itemEl.style.top = (ty - 22) + 'px';
            itemEl.innerHTML = `
                <span class="fan-menu__item-icon">${item.icon}</span>
                <span class="fan-menu__item-name">${item.name}</span>
            `;
            itemEl.addEventListener('click', (e) => {
                e.stopPropagation();
                this._triggerShortcut(item);
                this._collapse();
            });
            fanContainer.appendChild(itemEl);
        });

        document.body.appendChild(fanContainer);

        // Click outside to collapse
        setTimeout(() => {
            document.addEventListener('click', this._boundHandleClose);
        }, 0);
    }

    _collapse() {
        this.expanded = false;
        const fan = document.getElementById('fan-menu-container');
        if (fan) fan.remove();
        document.removeEventListener('click', this._boundHandleClose);
        this.render();
    }

    _handleOutsideClick(e) {
        const ball = this.container.querySelector('#floating-ball-main');
        const fan = document.getElementById('fan-menu-container');
        if (ball && ball.contains(e.target)) return;
        if (fan && fan.contains(e.target)) return;
        this._collapse();
    }

    _triggerShortcut(shortcut) {
        const actions = shortcut.actions || (shortcut.action ? [shortcut.action] : []);
        if (actions.length === 0) return;

        let cancelled = false;
        let actionIndex = 0;

        // Esc to cancel within 200ms window
        const onKeyDown = (e) => {
            if (e.key === 'Escape') {
                cancelled = true;
                document.removeEventListener('keydown', onKeyDown);
            }
        };
        document.addEventListener('keydown', onKeyDown);
        setTimeout(() => document.removeEventListener('keydown', onKeyDown), 200);

        const executeNext = () => {
            if (cancelled || actionIndex >= actions.length) return;
            const action = actions[actionIndex];
            actionIndex++;

            switch (action.type) {
                case 'chat_message':
                    bus.emit('chat-send', action.text);
                    break;
                case 'delay':
                    setTimeout(executeNext, action.ms || 1000);
                    return; // don't call executeNext immediately
                case 'chart':
                    bus.emit('view-source-changed', { slot: 0, source: 'chart', chartType: action.chart });
                    break;
                case 'command':
                    bus.emit('command', action.command);
                    break;
                default:
                    console.log('[FloatingBall] unknown action type:', action.type);
            }
            executeNext();
        };

        executeNext();
    }

    _enterEditMode() {
        bus.emit('open-shortcut-editor');
    }

    _loadShortcuts() {
        try {
            const saved = JSON.parse(localStorage.getItem('floating-ball-shortcuts'));
            if (Array.isArray(saved) && saved.length > 0) {
                // Migrate old format (single action) to new format (actions array)
                return saved.map(item => {
                    if (item.actions) return item; // already new format
                    if (item.action) return { ...item, actions: [item.action] }; // migrate
                    return item;
                });
            }
        } catch (e) {
            // ignore
        }
        return DEFAULT_SHORTCUTS;
    }

    _positionDefault() {
        const ball = this.container.querySelector('#floating-ball-main');
        if (!ball) return;
        ball.style.position = 'fixed';
        ball.style.right = '16px';
        ball.style.bottom = '100px';
    }
}

export { FloatingBall };
