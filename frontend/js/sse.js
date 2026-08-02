/**
 * SSE Manager — Server-Sent Events via POST (streaming chat responses).
 * Parses a custom event format from a text/event-stream response.
 *
 * Events:
 *   - text: plain text chunks appended to the chat message
 *   - tool_call_start: agent is about to call a tool
 *   - tool_call_result: result of a tool call
 *   - plan: a structured flight plan is being proposed
 *   - error: an error occurred on the server
 *   - [done]: stream complete
 */

class SseManager {
    /**
     * Send a message to the SSE endpoint and process the stream.
     * @param {string} endpoint - full URL or path
     * @param {string} text - user message text
     * @param {object} callbacks
     * @param {Function} callbacks.onMessage - (textChunk: string) => void
     * @param {Function} callbacks.onToolCall - (toolName: string, args: object) => void
     * @param {Function} callbacks.onToolResult - (toolName: string, result: any) => void
     * @param {Function} callbacks.onPlan - (plan: object) => void
     * @param {Function} callbacks.onComplete - (fullText: string) => void
     * @param {Function} callbacks.onError - (error: string) => void
     * @param {Function} [callbacks.onAbort] - (partialText: string) => void, abort 时调用（替代 onComplete）
     * @param {AbortSignal} [signal] - optional abort signal to cancel
     * @returns {Promise<void>}
     */
    async sendMessage(endpoint, text, callbacks, signal) {
        const {
            onMessage = () => {},
            onToolCall = () => {},
            onToolResult = () => {},
            onPlan = () => {},
            onComplete = () => {},
            onError = () => {},
            onAbort = null,
        } = callbacks;

        let fullText = ''; // try 外声明: abort catch 分支也需要访问 (避免 ReferenceError)
        try {
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'text/event-stream',
                },
                body: JSON.stringify({ message: text }),
                signal,
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let currentEvent = '';
            let errored = false; // error 事件后跳过 onComplete，避免重复渲染

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });

                // Parse SSE lines
                const lines = buffer.split('\n');
                // Keep the last incomplete line in the buffer
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (line.startsWith('event: ')) {
                        currentEvent = line.slice(7).trim();
                    } else if (line.startsWith('data: ')) {
                        const data = line.slice(6);
                        this._processEvent(currentEvent, data, {
                            onMessage,
                            onToolCall,
                            onToolResult,
                            onPlan,
                            onError,
                            fullTextAcc: (chunk) => { fullText += chunk; },
                        });
                        if (currentEvent === 'error') errored = true;
                        currentEvent = '';
                    } else if (line === '') {
                        currentEvent = ''; // empty line = event boundary
                    }
                }
            }

            // Notify completion (error 事件后不调用，避免与 onError 重复渲染)
            if (!errored) {
                onComplete(fullText);
            }

        } catch (e) {
            if (e.name === 'AbortError') {
                console.log('[SSE] request aborted');
                // 中断时不渲染空消息：交给 onAbort 回调（若有）
                if (typeof onAbort === 'function') {
                    onAbort(fullText || '');
                }
                return;
            }
            console.error('[SSE] error:', e);
            onError(e.message || String(e));
        }
    }

    /**
     * Process a single SSE event.
     */
    _processEvent(eventType, data, callbacks) {
        const { onMessage, onToolCall, onToolResult, onPlan, onError, fullTextAcc } = callbacks;

        switch (eventType) {
            case 'text':
                try {
                    const parsed = JSON.parse(data);
                    const content = parsed.content || data;
                    onMessage(content);
                    fullTextAcc(content);
                } catch {
                    onMessage(data);
                    fullTextAcc(data);
                }
                break;

            case 'tool_call_start': {
                try {
                    const parsed = JSON.parse(data);
                    onToolCall(parsed.name, parsed.args || {});
                } catch {
                    onToolCall('unknown', { raw: data });
                }
                break;
            }

            case 'tool_call_result': {
                try {
                    const parsed = JSON.parse(data);
                    onToolResult(parsed.name || 'unknown', parsed.result);
                } catch {
                    onToolResult('unknown', data);
                }
                break;
            }

            case 'plan': {
                try {
                    const plan = JSON.parse(data);
                    onPlan(plan);
                } catch {
                    console.warn('[SSE] could not parse plan:', data);
                }
                break;
            }

            case 'error':
                try {
                    const parsed = JSON.parse(data);
                    onError(parsed.message || data);
                } catch {
                    onError(data);
                }
                break;

            default:
                // Ignore unknown event types
                break;
        }
    }
}

export { SseManager };
