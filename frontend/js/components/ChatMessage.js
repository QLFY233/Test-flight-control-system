/**
 * ChatMessage — Renders individual chat messages.
 * Types: human, agent, tool_call, tool_result, system (alert, alpha_output)
 */

class ChatMessage {
    /**
     * Create a ChatMessage element.
     * @param {object} msg
     * @param {string} msg.role - 'human' | 'agent' | 'tool_call' | 'tool_result' | 'system'
     * @param {string} msg.content - message text/content
     * @param {string} [msg.subtype] - for system: 'alert-error', 'alert-warning', 'alert-info', 'alpha_output'
     * @param {string} [msg.toolName] - for tool_call/tool_result
     * @param {object|string} [msg.toolArgs] - for tool_call
     * @param {number} [msg.timestamp] - epoch ms
     * @returns {HTMLElement}
     */
    static render(msg) {
        const { role, content, subtype, toolName, toolArgs, timestamp } = msg;

        let cssClass = `chat-message chat-message--${role}`;
        if (subtype) {
            cssClass += ` chat-message--${subtype}`;
        }

        const time = timestamp ? new Date(timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) : '';

        const wrapper = document.createElement('div');
        wrapper.className = cssClass;

        if (role === 'tool_call') {
            // Collapsible tool call card
            const argsStr = toolArgs ? (typeof toolArgs === 'string' ? toolArgs : JSON.stringify(toolArgs, null, 2)) : '';
            wrapper.innerHTML = `
                <div class="tool-call-card">
                    <div class="tool-call-card__header">
                        <span class="tool-call-card__header-icon">&#9881;</span>
                        <span>${toolName || 'Tool Call'}</span>
                    </div>
                    <div class="tool-call-card__body">${ChatMessage._escapeHtml(argsStr)}</div>
                </div>
            `;

            const header = wrapper.querySelector('.tool-call-card__header');
            const body = wrapper.querySelector('.tool-call-card__body');
            header.addEventListener('click', () => {
                body.classList.toggle('tool-call-card__body--collapsed');
            });

        } else if (role === 'tool_result') {
            // Tool result card
            const resultStr = typeof content === 'string' ? content : JSON.stringify(content, null, 2);
            wrapper.innerHTML = `
                <div class="tool-call-card">
                    <div class="tool-call-card__header">
                        <span class="tool-call-card__header-icon">&#10003;</span>
                        <span>${toolName || 'Result'}</span>
                    </div>
                    <div class="tool-call-card__body">${ChatMessage._escapeHtml(resultStr)}</div>
                </div>
            `;
            const header = wrapper.querySelector('.tool-call-card__header');
            const body = wrapper.querySelector('.tool-call-card__body');
            header.addEventListener('click', () => {
                body.classList.toggle('tool-call-card__body--collapsed');
            });

        } else {
            // Regular message bubble
            let displayContent = content || '';
            // Simple markdown: bold, italic, code, pre
            displayContent = ChatMessage._simpleMarkdown(displayContent);

            wrapper.innerHTML = `
                <div class="chat-message__bubble">${displayContent}</div>
                ${time ? `<div class="chat-message__time">${time}</div>` : ''}
            `;
        }

        return wrapper;
    }

    /**
     * Very simple markdown-like rendering.
     * Supports: **bold**, *italic*, `code`, ```code blocks```, line breaks
     */
    static _simpleMarkdown(text) {
        if (!text) return '';
        let html = ChatMessage._escapeHtml(text);

        // Code blocks (multi-line)
        html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');

        // Inline code
        html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

        // Bold
        html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

        // Italic
        html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');

        // Line breaks
        html = html.replace(/\n/g, '<br>');

        return html;
    }

    static _escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

export { ChatMessage };
