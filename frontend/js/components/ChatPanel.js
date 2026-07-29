/**
 * ChatPanel — Global Beta Chat Dock (persists across page navigation).
 * Per spec P1/C2: 常驻,跨页面/Tab位置不变,仅初始化一次。
 * System messages (alert/alpha_output/status) inserted into this stream.
 */

import store from '../state.js';
import bus from '../event-bus.js';
import { sseManager, wsManager, config } from '../shared.js';
import { ChatMessage } from './ChatMessage.js';

class ChatPanel {
    constructor(container) {
        this.container = container;
        this.isRecording = false;
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.streamingMessageEl = null;
        this.streamingContent = '';
        this._boundHandleChatSend = this._handleChatSend.bind(this);
        this._mounted = false;
    }

    mount() {
        if (this._mounted) return;
        this._mounted = true;
        this.render();
        bus.on('chat-send', this._boundHandleChatSend);

        // Listen for alerts to show in chat
        bus.on('alert', (payload) => {
            this._addSystemMessage('alert-' + (payload.level || 'info'), payload.message || JSON.stringify(payload));
        });

        bus.on('alpha-output', (payload) => {
            if (payload && payload.action_sequence) {
                this._addSystemMessage('alpha_output', `[α] 动作序列: ${payload.action_sequence.length} 条`);
            }
        });
    }

    render() {
        const messages = store.get('chatHistory') || [];

        this.container.innerHTML = `
            <div class="chat-sidebar__header">
                <span class="chat-sidebar__header-title">[ BETA AI ]</span>
            </div>
            <div class="chat-sidebar__body">
                <div class="chat-sidebar__messages" id="chat-messages">
                    ${messages.length === 0 ? '<div class="chat-sidebar__empty">/// BETA AI 就绪<br>输入指令开始对话</div>' : ''}
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
                msgContainer.appendChild(el);
            });
            this._scrollToBottom(msgContainer);
        }

        this._bindEvents();
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

        // 流式占位元素 — 流式期间只显示纯文本，完成后替换为 Markdown 渲染版
        const streamEl = document.createElement('div');
        streamEl.className = 'chat-message chat-message--agent';
        const bubble = document.createElement('div');
        bubble.className = 'chat-message__bubble';
        bubble.textContent = '...';
        streamEl.appendChild(bubble);
        msgContainer.appendChild(streamEl);
        this.streamingMessageEl = streamEl;
        this.streamingContent = '';
        this._scrollToBottom(msgContainer);

        await sseManager.sendMessage(sseEndpoint, text, {
            onMessage: (chunk) => {
                this.streamingContent += chunk;
                // 流式期间只显示纯文本，不做 Markdown 渲染（防止表格/列表碎片化）
                if (bubble) bubble.textContent = this.streamingContent;
                this._scrollToBottom(msgContainer);
            },
            onToolCall: (toolName, args) => {
                const toolMsg = { role: 'tool_call', toolName, toolArgs: args, timestamp: Date.now() };
                msgContainer.appendChild(ChatMessage.render(toolMsg));
                this._scrollToBottom(msgContainer);
            },
            onToolResult: (toolName, result) => {
                const toolMsg = { role: 'tool_result', toolName, content: typeof result === 'string' ? result : JSON.stringify(result, null, 2), timestamp: Date.now() };
                msgContainer.appendChild(ChatMessage.render(toolMsg));
                this._scrollToBottom(msgContainer);
            },
            onPlan: (plan) => bus.emit('plan-received', plan),
            onComplete: (fullText) => {
                // 用完整 Markdown 渲染版替换流式占位
                const finalEl = ChatMessage.render({ role: 'agent', content: fullText || this.streamingContent, timestamp: Date.now() });
                if (this.streamingMessageEl && this.streamingMessageEl.parentNode) {
                    this.streamingMessageEl.replaceWith(finalEl);
                } else if (msgContainer) {
                    msgContainer.appendChild(finalEl);
                }
                this.streamingMessageEl = null;
                this._scrollToBottom(msgContainer);
                this._addMessage('agent', fullText || this.streamingContent);
            },
            onError: (error) => {
                const content = this.streamingContent || '';
                const finalEl = ChatMessage.render({ role: 'agent', content: content + '\n\n*[ERR: ' + error + ']*', timestamp: Date.now() });
                if (this.streamingMessageEl && this.streamingMessageEl.parentNode) {
                    this.streamingMessageEl.replaceWith(finalEl);
                } else if (msgContainer) {
                    msgContainer.appendChild(finalEl);
                }
                this.streamingMessageEl = null;
                this._scrollToBottom(msgContainer);
                this._addMessage('agent', content || ('ERR: ' + error));
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
