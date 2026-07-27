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
        } = callbacks;

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
            let fullText = '';
            let currentEvent = '';

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
                        currentEvent = '';
                    } else if (line === '') {
                        currentEvent = ''; // empty line = event boundary
                    }
                }
            }

            // Notify completion
            onComplete(fullText);

        } catch (e) {
            if (e.name === 'AbortError') {
                console.log('[SSE] request aborted');
                onComplete('');
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
                onMessage(data);
                fullTextAcc(data);
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
                onError(data);
                break;

            default:
                // Ignore unknown event types
                break;
        }
    }
}

export { SseManager };
