/**
 * ChatMessage — Renders individual chat messages.
 * Types: human, agent, tool_call, tool_result, system (alert, alpha_output)
 */

import { esc } from '../escape.js';

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
                        <span>${esc(toolName || 'Tool Call')}</span>
                    </div>
                    <div class="tool-call-card__body">${esc(argsStr)}</div>
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
                        <span>${esc(toolName || 'Result')}</span>
                    </div>
                    <div class="tool-call-card__body">${esc(resultStr)}</div>
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
     * Markdown-like rendering.
     * Supports: tables, headings, **bold**, *italic*, `code`, ```code blocks```,
     *           - lists, --- hr, line breaks
     */
    static _simpleMarkdown(text) {
        if (!text) return '';
        let html = esc(text);

        // Code blocks (multi-line) — do before line breaks
        html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');

        // Inline code
        html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

        // Bold
        html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

        // Italic — 无 lookbehind 写法（Safari < 16.4 不支持 (?<!..)，避免整个模块语法错误）
        // **bold** 已在上一步转成 <strong>，此处剩余的 * 均为单星号
        html = html.replace(/\*([^*\n]+)\*/g, '<em>$1</em>');

        // Headings (### Title)
        html = html.replace(/^### (.+)$/gm, '<h4>$1</h4>');
        html = html.replace(/^## (.+)$/gm, '<h3>$1</h3>');

        // Horizontal rule
        html = html.replace(/^---$/gm, '<hr>');

        // Tables — find blocks of |...| lines
        const lines = html.split('\n');
        const result = [];
        let inTable = false;
        let tableRows = [];
        let hasHeader = false;

        for (let i = 0; i < lines.length; i++) {
            const line = lines[i].trim();
            if (/^\|.+\|$/.test(line)) {
                // Separator row?
                if (/^\|[-:\s|]+\|$/.test(line)) {
                    hasHeader = true;
                    continue;
                }
                tableRows.push(line);
                inTable = true;
            } else {
                if (inTable && tableRows.length > 0) {
                    result.push(_buildTable(tableRows, hasHeader));
                    tableRows = [];
                    hasHeader = false;
                }
                inTable = false;
                result.push(line);
            }
        }
        // Flush remaining table
        if (inTable && tableRows.length > 0) {
            result.push(_buildTable(tableRows, hasHeader));
        }
        html = result.join('\n');

        // Unordered lists — protect newlines inside to keep <br> out
        html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
        html = html.replace(/(<li>.*?<\/li>\s*)+/g, '<ul>$&</ul>');

        // Line breaks (after block elements)
        html = html.replace(/\n/g, '<br>');

        // Strip <br> from inside block elements where they don't belong
        html = html.replace(/<(ul|table|h[1-6]|pre)>([\s\S]*?)<\/\1>/g, (m, tag, inner) => {
            return '<' + tag + '>' + inner.replace(/<br>/g, '') + '</' + tag + '>';
        });

        return html;
    }
}

/**
 * Build HTML table from markdown table rows.
 * @param {string[]} rows — lines like "| col1 | col2 |"
 * @param {boolean} hasHeader — first row is header
 * @returns {string} <table> HTML
 */
function _buildTable(rows, hasHeader) {
    if (rows.length === 0) return '';
    let html = '<table>';
    for (let i = 0; i < rows.length; i++) {
        const cells = rows[i].split('|').filter(c => c.trim() !== '');
        const tag = (hasHeader && i === 0) ? 'th' : 'td';
        html += '<tr>' + cells.map(c => `<${tag}>${c.trim()}</${tag}>`).join('') + '</tr>';
    }
    html += '</table>';
    return html;
}

export { ChatMessage };
