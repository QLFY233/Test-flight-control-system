/**
 * ShortcutEditor — Modal dialog for editing floating ball shortcuts.
 * Allows: name input, icon selector, action sequence editing, record mode.
 * Shortcuts are stored in localStorage under 'floating-ball-shortcuts'.
 */

import bus from '../event-bus.js';

const AVAILABLE_ICONS = [
    { emoji: '\u{1F4AC}', label: '对话' },
    { emoji: '\u{1F4CA}', label: '图表' },
    { emoji: '\u{1F3E0}', label: '回家' },
    { emoji: '\u{2709}', label: '消息' },
    { emoji: '\u{1F4F7}', label: '拍照' },
    { emoji: '\u{1F4CC}', label: '标记' },
    { emoji: '\u{2699}', label: '设置' },
    { emoji: '\u{1F6A8}', label: '警报' },
    { emoji: '\u{1F3AF}', label: '目标' },
    { emoji: '\u{1F4CD}', label: '定位' },
    { emoji: '\u{1F504}', label: '刷新' },
    { emoji: '\u{1F50D}', label: '搜索' },
];

class ShortcutEditor {
    constructor() {
        this.shortcuts = this._load();
        this.recording = false;
        this.recordingIndex = -1;
        this.recordedActions = [];
        this.container = null;

        // Listen for open event from FloatingBall
        bus.on('open-shortcut-editor', () => this.open());
    }

    /**
     * Open the shortcut editor modal.
     */
    open() {
        // Remove existing modal
        const existing = document.getElementById('shortcut-editor-overlay');
        if (existing) existing.remove();

        this.shortcuts = this._load();

        const overlay = document.createElement('div');
        overlay.className = 'overlay overlay--modal';
        overlay.id = 'shortcut-editor-overlay';

        overlay.innerHTML = `
            <div class="modal">
                <div class="modal__header">
                    <span>快捷操作编辑</span>
                    <button class="btn btn--icon btn--sm" id="shortcut-editor-close">&#10005;</button>
                </div>
                <div class="modal__body">
                    <div class="shortcut-editor__list" id="shortcut-editor-list">
                        ${this._renderList()}
                    </div>
                    <div style="margin-top: var(--space-md); text-align: center;">
                        <button class="btn btn--secondary btn--sm" id="shortcut-editor-add">+ 添加快捷操作</button>
                    </div>
                </div>
                <div class="modal__footer">
                    <button class="btn btn--ghost btn--sm" id="shortcut-editor-reset">恢复默认</button>
                    <button class="btn btn--primary btn--sm" id="shortcut-editor-save">保存</button>
                </div>
            </div>
        `;

        this.container = overlay;
        document.body.appendChild(overlay);

        // Close on overlay click
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) this.close();
        });

        // Close button
        overlay.querySelector('#shortcut-editor-close')?.addEventListener('click', () => this.close());

        // Add shortcut
        overlay.querySelector('#shortcut-editor-add')?.addEventListener('click', () => {
            this.shortcuts.push({ icon: '\u{1F4AC}', name: '新快捷操作', action: { type: 'chat_message', text: '' } });
            this._refreshList();
        });

        // Reset
        overlay.querySelector('#shortcut-editor-reset')?.addEventListener('click', () => {
            if (confirm('确定恢复默认快捷操作吗？')) {
                localStorage.removeItem('floating-ball-shortcuts');
                this.shortcuts = this._load();
                this._refreshList();
            }
        });

        // Save
        overlay.querySelector('#shortcut-editor-save')?.addEventListener('click', () => {
            this._save();
            bus.emit('shortcuts-updated', this.shortcuts);
            this.close();
        });

        this._bindListEvents();
    }

    /**
     * Close the editor.
     */
    close() {
        if (this.container) {
            this.container.remove();
            this.container = null;
        }
    }

    // ---- Internal ----

    _renderList() {
        if (this.shortcuts.length === 0) {
            return '<div style="text-align: center; color: var(--color-text-disabled); padding: var(--space-xl);">暂无快捷操作</div>';
        }

        return this.shortcuts.map((item, i) => `
            <div class="shortcut-editor__item" data-index="${i}">
                <span class="shortcut-editor__item-icon" id="shortcut-icon-${i}">${item.icon}</span>
                <input type="text" class="shortcut-editor__item-input" value="${this._escAttr(item.name)}" placeholder="名称" data-index="${i}" data-field="name">
                <button class="btn btn--icon btn--sm change-icon-btn" data-index="${i}" title="更换图标">&#9650;</button>
                <button class="btn btn--icon btn--sm record-btn ${this.recording && this.recordingIndex === i ? 'btn--danger' : ''}" data-index="${i}" title="${this.recording && this.recordingIndex === i ? '停止录制' : '录制动作'}">
                    ${this.recording && this.recordingIndex === i ? '&#9632;' : '&#9679;'}
                </button>
                <button class="btn btn--icon btn--sm delete-shortcut-btn" data-index="${i}" title="删除">&#10005;</button>
            </div>
        `).join('');
    }

    _refreshList() {
        const listEl = this.container?.querySelector('#shortcut-editor-list');
        if (!listEl) return;
        listEl.innerHTML = this._renderList();
        this._bindListEvents();
    }

    _bindListEvents() {
        const listEl = this.container?.querySelector('#shortcut-editor-list');
        if (!listEl) return;

        // Name input changes
        listEl.querySelectorAll('.shortcut-editor__item-input').forEach(input => {
            input.addEventListener('input', () => {
                const idx = parseInt(input.dataset.index);
                const field = input.dataset.field;
                if (!isNaN(idx) && this.shortcuts[idx]) {
                    this.shortcuts[idx][field] = input.value;
                }
            });
        });

        // Change icon buttons
        listEl.querySelectorAll('.change-icon-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const idx = parseInt(btn.dataset.index);
                if (isNaN(idx) || !this.shortcuts[idx]) return;
                // Cycle through available icons
                const currentIcon = this.shortcuts[idx].icon;
                const currentIdx = AVAILABLE_ICONS.findIndex(ic => ic.emoji === currentIcon);
                const nextIdx = (currentIdx + 1) % AVAILABLE_ICONS.length;
                this.shortcuts[idx].icon = AVAILABLE_ICONS[nextIdx].emoji;

                const iconSpan = listEl.querySelector(`#shortcut-icon-${idx}`);
                if (iconSpan) iconSpan.textContent = AVAILABLE_ICONS[nextIdx].emoji;
            });
        });

        // Record buttons
        listEl.querySelectorAll('.record-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const idx = parseInt(btn.dataset.index);
                if (isNaN(idx) || !this.shortcuts[idx]) return;

                if (this.recording && this.recordingIndex === idx) {
                    this._stopRecording();
                } else {
                    this._startRecording(idx);
                }
                this._refreshList();
            });
        });

        // Delete buttons
        listEl.querySelectorAll('.delete-shortcut-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const idx = parseInt(btn.dataset.index);
                if (!isNaN(idx)) {
                    if (confirm(`确定删除快捷操作 "${this.shortcuts[idx]?.name}" 吗？`)) {
                        this.shortcuts.splice(idx, 1);
                        this._refreshList();
                    }
                }
            });
        });
    }

    _startRecording(index) {
        this.recording = true;
        this.recordingIndex = index;
        this.recordedActions = [];

        // Listen for chat send events
        this._boundRecordChat = (text) => {
            this.recordedActions.push({ type: 'chat_message', text });
        };
        bus.on('chat-send', this._boundRecordChat);

        // Auto-stop after 30 seconds
        this._recordTimeout = setTimeout(() => {
            this._stopRecording();
            this._refreshList();
        }, 30000);
    }

    _stopRecording() {
        if (!this.recording) return;

        if (this._boundRecordChat) {
            bus.off('chat-send', this._boundRecordChat);
            this._boundRecordChat = null;
        }

        if (this._recordTimeout) {
            clearTimeout(this._recordTimeout);
            this._recordTimeout = null;
        }

        // Save recorded actions
        if (this.recordedActions.length > 0 && this.shortcuts[this.recordingIndex]) {
            // Store the sequence (last action in sequence, or combine)
            // For simplicity, store the first chat message action
            const chatAction = this.recordedActions.find(a => a.type === 'chat_message');
            if (chatAction) {
                this.shortcuts[this.recordingIndex].action = chatAction;
            }
        }

        this.recording = false;
        this.recordingIndex = -1;
        this.recordedActions = [];
    }

    _load() {
        try {
            const saved = JSON.parse(localStorage.getItem('floating-ball-shortcuts'));
            if (Array.isArray(saved) && saved.length > 0) return saved;
        } catch {
            // ignore
        }
        return [
            { icon: '\u{1F4AC}', name: '发送预设1', action: { type: 'chat_message', text: '请规划飞行路径' } },
            { icon: '\u{1F4CA}', name: '查看高度图', action: { type: 'chart', chart: 'altitude' } },
            { icon: '\u{1F3E0}', name: '回到原点', action: { type: 'command', command: 'go_home' } },
            { icon: '\u{2709}', name: '发送预设2', action: { type: 'chat_message', text: '当前状态如何？' } },
        ];
    }

    _save() {
        localStorage.setItem('floating-ball-shortcuts', JSON.stringify(this.shortcuts));
    }

    _escAttr(str) {
        return String(str || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }
}

export { ShortcutEditor };
