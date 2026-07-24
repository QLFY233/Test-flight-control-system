/**
 * ChatPanel — Global Beta Chat Dock (persists across page navigation).
 * Handles SSE streaming, voice input, and system messages.
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
    }

    mount() {
        this.render();
        store.subscribe('ui.chatOpen', (val) => this._syncVisibility());
        store.subscribe('ui.chatCollapsed', () => this.render());
        bus.on('chat-send', this._boundHandleChatSend);

        // Listen for alerts to show in chat
        bus.on('alert', (payload) => {
            this._addSystemMessage('alert-' + (payload.level || 'info'), payload.message || JSON.stringify(payload));
        });

        bus.on('alpha-output', (payload) => {
            if (payload && payload.action_sequence) {
                this._addSystemMessage('alpha_output', `动作序列更新: ${payload.action_sequence.length} 条动作`);
            } else if (payload && payload.waypoints) {
                this._addSystemMessage('alpha_output', `轨迹更新: ${payload.waypoints.length} 个航点`);
            }
        });
    }

    render() {
        const isCollapsed = store.get('ui.chatCollapsed');
        const messages = store.get('chatHistory') || [];

        this.container.innerHTML = `
            <div class="chat-dock ${isCollapsed ? 'chat-dock--collapsed' : ''}" id="chat-dock-inner">
                <div class="chat-dock__header" id="chat-dock-header">
                    <span class="chat-dock__header-title">Beta 对话</span>
                    <div class="chat-dock__header-actions">
                        <button class="btn btn--icon btn--sm" id="chat-btn-collapse" title="${isCollapsed ? '展开' : '折叠'}">
                            ${isCollapsed ? '&#9650;' : '&#9660;'}
                        </button>
                        <button class="btn btn--icon btn--sm" id="chat-btn-close" title="关闭">&#10005;</button>
                    </div>
                </div>
                <div class="chat-dock__body">
                    <div class="chat-dock__messages" id="chat-messages"></div>
                    <div class="chat-dock__input">
                        <button class="btn btn--icon btn--sm" id="chat-btn-voice" title="按住录音">
                            &#127908;
                        </button>
                        <textarea class="chat-dock__input-field" id="chat-input" placeholder="输入消息..." rows="1"></textarea>
                        <button class="btn btn--primary btn--sm" id="chat-btn-send">发送</button>
                    </div>
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

        // Bind events
        this._bindEvents();
    }

    _bindEvents() {
        const header = this.container.querySelector('#chat-dock-header');
        const collapseBtn = this.container.querySelector('#chat-btn-collapse');
        const closeBtn = this.container.querySelector('#chat-btn-close');
        const sendBtn = this.container.querySelector('#chat-btn-send');
        const voiceBtn = this.container.querySelector('#chat-btn-voice');
        const inputField = this.container.querySelector('#chat-input');

        if (header) {
            header.addEventListener('click', (e) => {
                if (e.target.closest('button')) return;
                const collapsed = store.get('ui.chatCollapsed');
                store.set('ui.chatCollapsed', !collapsed);
                this.render();
            });
        }

        if (collapseBtn) {
            collapseBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                const collapsed = store.get('ui.chatCollapsed');
                store.set('ui.chatCollapsed', !collapsed);
                this.render();
            });
        }

        if (closeBtn) {
            closeBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                store.set('ui.chatOpen', false);
                this.container.innerHTML = '';
            });
        }

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
            voiceBtn.addEventListener('mouseleave', () => {
                if (this.isRecording) this._stopRecording();
            });
            voiceBtn.addEventListener('touchstart', (e) => {
                e.preventDefault();
                this._startRecording();
            });
            voiceBtn.addEventListener('touchend', (e) => {
                e.preventDefault();
                this._stopRecording();
            });
        }
    }

    /**
     * Send a user message and stream the response.
     */
    async _sendMessage(text) {
        // Add user message
        this._addMessage('human', text);

        // Start SSE stream
        const sseEndpoint = (config?.backend?.base_url || 'http://localhost:8000') + (config?.backend?.sse_beta || '/api/chat/beta');

        // Create streaming agent message placeholder
        const msgContainer = this.container.querySelector('#chat-messages');
        if (!msgContainer) return;

        const streamEl = document.createElement('div');
        streamEl.className = 'chat-message chat-message--agent';
        const bubble = document.createElement('div');
        bubble.className = 'chat-message__bubble';
        bubble.textContent = '思考中...';
        streamEl.appendChild(bubble);
        msgContainer.appendChild(streamEl);
        this.streamingMessageEl = streamEl;
        this.streamingContent = '';

        this._scrollToBottom(msgContainer);

        let currentToolCallEl = null;

        await sseManager.sendMessage(sseEndpoint, text, {
            onMessage: (chunk) => {
                this.streamingContent += chunk;
                if (bubble) {
                    // Simple rendering as we go
                    bubble.innerHTML = ChatMessage._simpleMarkdown(this.streamingContent);
                }
                this._scrollToBottom(msgContainer);
            },
            onToolCall: (toolName, args) => {
                // Add a tool call card after the streaming message
                const toolMsg = { role: 'tool_call', toolName, toolArgs: args, timestamp: Date.now() };
                const toolEl = ChatMessage.render(toolMsg);
                currentToolCallEl = toolEl;
                msgContainer.appendChild(toolEl);
                this._scrollToBottom(msgContainer);
            },
            onToolResult: (toolName, result) => {
                const toolMsg = {
                    role: 'tool_result',
                    toolName,
                    content: typeof result === 'string' ? result : JSON.stringify(result, null, 2),
                    timestamp: Date.now()
                };
                const toolEl = ChatMessage.render(toolMsg);
                msgContainer.appendChild(toolEl);
                this._scrollToBottom(msgContainer);
            },
            onPlan: (plan) => {
                bus.emit('plan-received', plan);
            },
            onComplete: (fullText) => {
                // Finalize the streaming message in store
                this._addMessage('agent', fullText);
            },
            onError: (error) => {
                if (bubble && !this.streamingContent) {
                    bubble.textContent = '错误: ' + error;
                    bubble.style.color = 'var(--color-error)';
                }
                this._addMessage('agent', this.streamingContent || ('错误: ' + error));
            },
        });
    }

    /**
     * Add a message to chat history.
     */
    _addMessage(role, content, extra = {}) {
        const msg = { role, content, timestamp: Date.now(), ...extra };
        const history = store.get('chatHistory') || [];
        store.set('chatHistory', [...history, msg]);
    }

    /**
     * Add a system message (displayed with special styling).
     */
    _addSystemMessage(subtype, content) {
        const msg = { role: 'system', content, subtype, timestamp: Date.now() };
        const history = store.get('chatHistory') || [];
        store.set('chatHistory', [...history, msg]);

        // Render immediately if chat is visible
        const msgContainer = this.container.querySelector('#chat-messages');
        if (msgContainer) {
            const el = ChatMessage.render(msg);
            msgContainer.appendChild(el);
            this._scrollToBottom(msgContainer);
        }
    }

    /**
     * Handle chat-send event from floating ball or other components.
     */
    _handleChatSend(text) {
        // Make sure chat is open
        store.set('ui.chatOpen', true);
        store.set('ui.chatCollapsed', false);
        this.render();
        // Small delay to let DOM update
        setTimeout(() => this._sendMessage(text), 100);
    }

    /**
     * Start voice recording via Web Audio API.
     */
    async _startRecording() {
        if (this.isRecording) return;
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            this.mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
            this.audioChunks = [];

            this.mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) this.audioChunks.push(e.data);
            };

            this.mediaRecorder.onstop = async () => {
                const blob = new Blob(this.audioChunks, { type: 'audio/webm' });
                // Convert to base64 and send via WebSocket
                const reader = new FileReader();
                reader.onloadend = () => {
                    const base64 = reader.result.split(',')[1];
                    wsManager.send('voice_frame', { audio: base64, format: 'webm' });
                };
                reader.readAsDataURL(blob);

                // Stop all tracks
                stream.getTracks().forEach(t => t.stop());
            };

            this.mediaRecorder.start();
            this.isRecording = true;

            const voiceBtn = this.container.querySelector('#chat-btn-voice');
            if (voiceBtn) {
                voiceBtn.style.color = 'var(--color-error)';
                voiceBtn.textContent = '⬤';
            }
        } catch (e) {
            console.error('[ChatPanel] microphone access denied:', e);
            alert('无法访问麦克风: ' + e.message);
        }
    }

    /**
     * Stop voice recording.
     */
    _stopRecording() {
        if (!this.isRecording || !this.mediaRecorder) return;
        this.mediaRecorder.stop();
        this.isRecording = false;
        this.mediaRecorder = null;

        const voiceBtn = this.container.querySelector('#chat-btn-voice');
        if (voiceBtn) {
            voiceBtn.style.color = '';
            voiceBtn.textContent = '🎤';
        }
    }

    _syncVisibility() {
        const open = store.get('ui.chatOpen');
        if (!open && this.container.innerHTML) {
            this.container.innerHTML = '';
        } else if (open && !this.container.querySelector('#chat-dock-inner')) {
            this.render();
        }
    }

    _scrollToBottom(container) {
        if (container) {
            container.scrollTop = container.scrollHeight;
        }
    }
}

export { ChatPanel };
