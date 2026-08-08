/**
 * ChatPanel — Global Beta Chat Dock (persists across page navigation).
 * Per spec P1/C2: 常驻,跨页面/Tab位置不变,仅初始化一次。
 * System messages (alert/alpha_output/status) inserted into this stream.
 */

import store from '../state.js';
import bus from '../event-bus.js';
import { sseManager, wsManager, config } from '../shared.js';
import { ChatMessage } from './ChatMessage.js';

// 快捷功能卡片（empty 态）：图标 + 标题 + 预设指令（点击复用 _sendMessage 发给 β）
const QUICK_ACTIONS = [
    { key: 'plan', icon: '✈', title: '飞行规划', text: '帮我规划一次飞行任务' },
    { key: 'history', icon: '⌚', title: '历史分析', text: '分析最近一次飞行的数据' },
    { key: 'data', icon: '〰', title: '数据处理', text: '对最近遥测数据做频谱分析' },
    { key: 'status', icon: '◉', title: '状态查询', text: '当前飞行状态如何' },
];

// alert level → 样式后缀（critical/error → error 红色；warning → 黄色；其余 → info 蓝色）
const ALERT_LEVEL_STYLE = { critical: 'error', error: 'error', warning: 'warning', info: 'info' };
// 同 code 防刷屏窗口：1s 内丢弃（B 侧 2s 节流的降级兜底）；10s 内折叠计数
const ALERT_THROTTLE_MS = 1000;
const ALERT_COLLAPSE_MS = 10000;

class ChatPanel {
    constructor(container) {
        this.container = container;
        this.isRecording = false;
        this.mediaRecorder = null;
        this.audioChunks = [];
        this._boundHandleChatSend = this._handleChatSend.bind(this);
        this._boundHandleAlert = this._handleAlert.bind(this);
        // alert 防刷屏：code → { count, lastTs, el, storeIndex }
        this._lastAlertMap = new Map();
        this._mounted = false;
    }

    mount() {
        if (this._mounted) return;
        this._mounted = true;
        this.render();
        bus.on('chat-send', this._boundHandleChatSend);

        // Listen for alerts to show in chat — 防刷屏: 同 code 节流+折叠计数 (见 _handleAlert)
        bus.on('alert', this._boundHandleAlert);

        bus.on('alpha-output', (payload) => {
            if (payload && payload.remaining_actions) {
                this._addSystemMessage('alpha_output', `[α] 动作序列: ${payload.remaining_actions.length} 条`);
            } else if (payload && payload.action_sequence) {
                // 兼容旧字段名
                this._addSystemMessage('alpha_output', `[α] 动作序列: ${payload.action_sequence.length} 条`);
            }
        });
    }

    /**
     * 组件销毁/页面卸载时清理：bus 监听 + alert 折叠状态（防御性；ChatPanel 全局常驻，通常不被卸载）。
     */
    unmount() {
        if (!this._mounted) return;
        this._mounted = false;
        this._lastAlertMap.clear();
        bus.off('chat-send', this._boundHandleChatSend);
        bus.off('alert', this._boundHandleAlert);
        if (this.container) this.container.innerHTML = '';
    }

    render() {
        const messages = store.get('chatHistory') || [];

        this.container.innerHTML = `
            <div class="chat-sidebar__header">
                <span class="chat-sidebar__header-title">[ BETA AI ]</span>
            </div>
            <div class="chat-sidebar__body">
                <div class="chat-sidebar__messages" id="chat-messages">
                    ${messages.length === 0 ? `
                        <div class="chat-sidebar__empty">
                            <div class="chat-quick-wrap">
                                <div>/// BETA AI 就绪<br>输入指令开始对话</div>
                                <div class="chat-quick-cards">
                                    ${QUICK_ACTIONS.map(a => `
                                        <button type="button" class="chat-quick-card" data-quick="${a.key}" title="${a.text}">
                                            <span class="chat-quick-card__icon">${a.icon}</span>
                                            <span class="chat-quick-card__title">${a.title}</span>
                                        </button>
                                    `).join('')}
                                </div>
                            </div>
                        </div>
                    ` : ''}
                </div>
                <div class="chat-sidebar__input">
                    <button class="btn btn--icon btn--sm" id="chat-btn-voice" title="语音输入">🎤</button>
                    <textarea class="chat-sidebar__input-field" id="chat-input" placeholder=">>> 输入指令..." rows="1"></textarea>
                    <button class="btn btn--primary btn--sm" id="chat-btn-send">发送</button>
                </div>
            </div>
        `;

        // Render existing messages
        const msgContainer = this.container.querySelector('#chat-messages');
        if (msgContainer) {
            messages.forEach(msg => {
                const el = ChatMessage.render(msg);
                // alert 消息附 code/计数徽标（store 里有 alertCode/alertCount 时）
                if (msg && msg.alertCode) this._attachAlertBadges(el, msg);
                msgContainer.appendChild(el);
            });
            this._scrollToBottom(msgContainer);
        }

        // DOM 已重建 → 旧 alert 折叠引用失效，重置（后续同 code 按新消息窗口处理；历史计数由 store 徽标保留）
        this._lastAlertMap = new Map();

        this._bindEvents();

        // TaskPanel 依赖表头重挂按钮 (render 整体重建 DOM)
        bus.emit('chat-panel-rendered', this.container);
    }

    _bindEvents() {
        const sendBtn = this.container.querySelector('#chat-btn-send');
        const voiceBtn = this.container.querySelector('#chat-btn-voice');
        const inputField = this.container.querySelector('#chat-input');

        if (sendBtn && inputField) {
            const send = () => {
                const text = inputField.value.trim();
                if (!text) return;
                this._sendMessage(text);
                inputField.value = '';
            };
            sendBtn.addEventListener('click', send);
            inputField.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    send();
                }
            });
        }

        if (voiceBtn) {
            voiceBtn.addEventListener('mousedown', () => this._startRecording());
            voiceBtn.addEventListener('mouseup', () => this._stopRecording());
            voiceBtn.addEventListener('mouseleave', () => { if (this.isRecording) this._stopRecording(); });
            voiceBtn.addEventListener('touchstart', (e) => { e.preventDefault(); this._startRecording(); });
            voiceBtn.addEventListener('touchend', (e) => { e.preventDefault(); this._stopRecording(); });
        }

        // 快捷功能卡片：点击 = 向 β 发送预设指令（复用 _sendMessage）
        this.container.querySelectorAll('.chat-quick-card').forEach(card => {
            card.addEventListener('click', () => {
                const act = QUICK_ACTIONS.find(a => a.key === card.dataset.quick);
                if (act && act.text) this._sendMessage(act.text);
            });
        });
    }

    /**
     * alert 防刷屏入口（bus 'alert' 监听）：
     *  - 同 code 1s 内 → 丢弃（对齐 B 侧 2s 节流的降级兜底）
     *  - 同 code 10s 内 → 不新增消息，仅更新上一条的计数徽标（折叠）
     *  - 否则 → 新增带 level 色的系统消息卡片（code 徽标 + 折叠计数徽标）
     */
    _handleAlert(payload) {
        if (!payload) return;
        const code = payload.code || 'alert';
        const detail = payload.detail || JSON.stringify(payload);
        const now = Date.now();
        const prev = this._lastAlertMap.get(code);

        if (prev) {
            const dt = now - prev.lastTs;
            if (dt < ALERT_THROTTLE_MS) return;                    // 节流：1s 内丢弃
            if (dt < ALERT_COLLAPSE_MS) {                          // 折叠：10s 内同 code → 计数 +1
                prev.count += 1;
                prev.lastTs = now;
                this._updateAlertCounter(prev.el, prev.count, prev.storeIndex);
                return;
            }
            this._lastAlertMap.delete(code);                       // 超窗 → 新消息
        }

        const level = ALERT_LEVEL_STYLE[payload.level || ''] || 'info';
        const msg = {
            role: 'system',
            content: detail,
            subtype: 'alert-' + level,
            alertCode: code,
            alertCount: 1,
            timestamp: now,
        };
        const history = store.get('chatHistory') || [];
        const storeIndex = history.length;
        store.set('chatHistory', [...history, msg]);

        const msgContainer = this.container.querySelector('#chat-messages');
        if (msgContainer) {
            const el = ChatMessage.render(msg);
            this._attachAlertBadges(el, msg);
            msgContainer.appendChild(el);
            this._scrollToBottom(msgContainer);
            this._lastAlertMap.set(code, { count: 1, lastTs: now, el, storeIndex });
        }
    }

    /**
     * 为 alert 消息元素附加徽标：code 前置 + 折叠计数后置（count > 1 时）。
     * 不修改 ChatMessage 渲染逻辑，仅作 DOM 增强。
     */
    _attachAlertBadges(el, msg) {
        if (!el || !msg || !msg.alertCode) return;
        const bubble = el.querySelector('.chat-message__bubble');
        if (!bubble) return;

        if (!bubble.querySelector('.chat-alert-code')) {
            const code = document.createElement('span');
            code.className = 'chat-alert-code';
            code.textContent = msg.alertCode;
            bubble.prepend(code);
        }
        if (msg.alertCount && msg.alertCount > 1) {
            if (!bubble.querySelector('.chat-alert-count')) {
                const badge = document.createElement('span');
                badge.className = 'chat-alert-count';
                badge.textContent = '×' + msg.alertCount;
                bubble.appendChild(badge);
            }
        }
    }

    /**
     * 折叠时更新上一条 alert 的计数：DOM 徽标 + store（render 重建后计数保留）。
     * @param {HTMLElement|null} prevEl 上一条消息元素（可能已被 DOM 重建移除）
     * @param {number} count 折叠后的总次数
     * @param {number} storeIndex chatHistory 中该消息的索引
     */
    _updateAlertCounter(prevEl, count, storeIndex) {
        if (prevEl && prevEl.isConnected) {
            let badge = prevEl.querySelector('.chat-alert-count');
            const bubble = prevEl.querySelector('.chat-message__bubble');
            if (!badge && bubble) {
                badge = document.createElement('span');
                badge.className = 'chat-alert-count';
                bubble.appendChild(badge);
            }
            if (badge) badge.textContent = '×' + count;
        }
        // 同步 store：render() 重建 DOM 后靠 store 徽标恢复计数
        if (storeIndex != null) {
            const history = store.get('chatHistory') || [];
            if (history[storeIndex]) {
                history[storeIndex] = { ...history[storeIndex], alertCount: count };
                store.set('chatHistory', history);
            }
        }
    }

    async _sendMessage(text) {
        // 先渲染用户消息到 DOM
        const msgContainer = this.container.querySelector('#chat-messages');
        if (!msgContainer) return;

        // 清除空状态
        const empty = msgContainer.querySelector('.chat-sidebar__empty');
        if (empty) empty.remove();

        // 添加用户消息到 store + DOM
        this._addMessage('human', text);
        const userMsg = { role: 'human', content: text, timestamp: Date.now() };
        msgContainer.appendChild(ChatMessage.render(userMsg));
        this._scrollToBottom(msgContainer);

        const sseEndpoint = (window.__app.config?.backend?.base_url || 'http://localhost:8000') + (window.__app.config?.backend?.sse_beta || '/api/chat/beta');

        // 流式占位元素 — 流式期间只显示纯文本，完成后替换为 Markdown 渲染版。
        // 流状态全部收敛到本闭包局部变量，杜绝并发请求相互覆盖（共享实例字段的竞态）。
        const streamEl = document.createElement('div');
        streamEl.className = 'chat-message chat-message--agent';
        const bubble = document.createElement('div');
        bubble.className = 'chat-message__bubble';
        bubble.textContent = '...';
        streamEl.appendChild(bubble);
        msgContainer.appendChild(streamEl);
        let streamContent = '';
        let errored = false; // error 事件后跳过 onComplete，避免重复渲染
        this._scrollToBottom(msgContainer);

        await sseManager.sendMessage(sseEndpoint, text, {
            onMessage: (chunk) => {
                streamContent += chunk;
                // 流式期间只显示纯文本，不做 Markdown 渲染（防止表格/列表碎片化）
                if (bubble) bubble.textContent = streamContent;
                this._scrollToBottom(msgContainer);
            },
            onToolCall: (_toolName, _args) => {
                // 工具调用是 β 的内部过程，不在用户对话区展示，避免连续轮询刷屏。
            },
            onToolResult: (_toolName, _result) => {
                // 工具结果已用于生成最终回复，不在用户对话区重复展示。
            },
            onPlan: (plan) => bus.emit('plan-received', plan),
            onComplete: (fullText) => {
                if (errored) return; // sse.js 错误后也会跳过 onComplete，这里双保险
                // 用完整 Markdown 渲染版替换流式占位
                const finalEl = ChatMessage.render({ role: 'agent', content: fullText || streamContent, timestamp: Date.now() });
                if (streamEl.parentNode) {
                    streamEl.replaceWith(finalEl);
                } else if (msgContainer) {
                    msgContainer.appendChild(finalEl);
                }
                this._scrollToBottom(msgContainer);
                this._addMessage('agent', fullText || streamContent);
            },
            onError: (error) => {
                errored = true;
                const content = streamContent || '';
                const finalEl = ChatMessage.render({ role: 'agent', content: content + '\n\n*[ERR: ' + error + ']*', timestamp: Date.now() });
                if (streamEl.parentNode) {
                    streamEl.replaceWith(finalEl);
                } else if (msgContainer) {
                    msgContainer.appendChild(finalEl);
                }
                this._scrollToBottom(msgContainer);
                this._addMessage('agent', content || ('ERR: ' + error));
            },
            onAbort: () => {
                // 中断时不渲染空消息：仅移除流式占位
                if (streamEl.parentNode) {
                    streamEl.remove();
                }
            },
        });
    }

    _addMessage(role, content, extra = {}) {
        const msg = { role, content, timestamp: Date.now(), ...extra };
        const history = store.get('chatHistory') || [];
        store.set('chatHistory', [...history, msg]);
    }

    _addSystemMessage(subtype, content) {
        const msg = { role: 'system', content, subtype, timestamp: Date.now() };
        const history = store.get('chatHistory') || [];
        store.set('chatHistory', [...history, msg]);
        const msgContainer = this.container.querySelector('#chat-messages');
        if (msgContainer) {
            msgContainer.appendChild(ChatMessage.render(msg));
            this._scrollToBottom(msgContainer);
        }
    }

    _handleChatSend(text) {
        store.set('ui.chatCollapsed', false);
        this.render();
        setTimeout(() => this._sendMessage(text), 100);
    }

    async _startRecording() {
        if (this.isRecording) return;
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            this.mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
            this.audioChunks = [];
            this.mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) this.audioChunks.push(e.data); };
            this.mediaRecorder.onstop = async () => {
                const blob = new Blob(this.audioChunks, { type: 'audio/webm' });
                const reader = new FileReader();
                reader.onloadend = () => {
                    const base64 = reader.result.split(',')[1];
                    wsManager.send('voice_frame', { audio: base64, format: 'webm' });
                };
                reader.readAsDataURL(blob);
                stream.getTracks().forEach(t => t.stop());
            };
            this.mediaRecorder.start();
            this.isRecording = true;
            const voiceBtn = this.container.querySelector('#chat-btn-voice');
            if (voiceBtn) { voiceBtn.style.color = 'var(--color-red)'; voiceBtn.textContent = '⬤'; }
        } catch (e) {
            console.error('[ChatPanel] microphone denied:', e);
        }
    }

    _stopRecording() {
        if (!this.isRecording || !this.mediaRecorder) return;
        this.mediaRecorder.stop();
        this.isRecording = false;
        this.mediaRecorder = null;
        const voiceBtn = this.container.querySelector('#chat-btn-voice');
        if (voiceBtn) { voiceBtn.style.color = ''; voiceBtn.textContent = '🎤'; }
    }

    _scrollToBottom(container) {
        if (container) container.scrollTop = container.scrollHeight;
    }
}

export { ChatPanel };
