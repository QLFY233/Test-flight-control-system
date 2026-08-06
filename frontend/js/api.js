/**
 * REST API Client — Typed HTTP methods with error handling.
 */

class ApiManager {
    constructor(baseUrl = 'http://localhost:8000') {
        this.baseUrl = baseUrl.replace(/\/+$/, '');
        // 超时默认值：config-default.json backend.request_timeout，缺省 10000ms
        this.defaultTimeout = window.__app?.config?.backend?.request_timeout || 10000;
    }

    /**
     * Update the base URL.
     */
    setBaseUrl(url) {
        this.baseUrl = url.replace(/\/+$/, '');
    }

    /**
     * GET request.
     * @param {string} path - e.g. '/api/overview'
     * @param {object} [params] - query parameters
     * @param {number} [timeout] - request timeout in ms (default: config/10000)
     * @returns {Promise<any>}
     */
    async get(path, params = {}, timeout) {
        return this._fetchWithTimeout('GET', path, params, undefined, timeout);
    }

    /**
     * POST request.
     * @param {string} path
     * @param {object} [body]
     * @returns {Promise<any>}
     */
    async post(path, body = {}) {
        return this._fetchWithTimeout('POST', path, {}, body);
    }

    /**
     * PATCH request.
     * @param {string} path
     * @param {object} [body]
     * @returns {Promise<any>}
     */
    async patch(path, body = {}) {
        return this._fetchWithTimeout('PATCH', path, {}, body);
    }

    /**
     * DELETE request.
     * @param {string} path
     * @returns {Promise<any>}
     */
    async delete(path) {
        return this._fetchWithTimeout('DELETE', path, {});
    }

    // ==========================================================
    // Domain Methods
    // ==========================================================

    /** GET /api/overview — dashboard overview data */
    async getOverview() {
        return this.get('/api/overview');
    }

    /** GET /api/sessions — list flight sessions */
    async getSessions(params = {}) {
        return this.get('/api/sessions', params);
    }

    /** GET /api/history/telemetry/{sid} — 会话遥测历史（对齐后端实际路由） */
    async getTelemetry(sessionId, params = {}) {
        return this.get(`/api/history/telemetry/${encodeURIComponent(sessionId)}`, params);
    }

    /** GET /api/history/conversations/{sid} — 会话对话历史（对齐后端实际路由） */
    async getConversations(sessionId) {
        return this.get(`/api/history/conversations/${encodeURIComponent(sessionId)}`);
    }

    /** GET /api/environments — saved environments */
    async getEnvironments() {
        return this.get('/api/environments');
    }

    /** POST /api/environments — save an environment preset */
    async saveEnvironment(env) {
        return this.post('/api/environments', env);
    }

    /** GET /api/current-pose — current drone pose（对齐后端实际路由） */
    async getCurrentPose() {
        return this.get('/api/current-pose');
    }

    /** POST /api/sessions — create a new flight session */
    async createSession(config) {
        return this.post('/api/sessions', config);
    }

    // ==========================================================
    // 任务管理 (任务 = flight session; 绑定 β/α 对话 + 飞行数据)
    // ==========================================================

    /** GET /api/sessions?limit=100 — 任务列表 (含对话/遥测计数, 任务面板用) */
    async getTaskList(limit = 100) {
        const res = await this.get('/api/sessions', { limit });
        return res?.sessions || [];
    }

    /** POST /api/sessions — 新建任务 (后端自动切换为当前会话) */
    async createTask(config = {}) {
        return this.post('/api/sessions', config);
    }

    /** PATCH /api/sessions/{id} — 重命名任务 */
    async renameTask(taskId, name) {
        return this.patch(`/api/sessions/${encodeURIComponent(taskId)}`, { task_description: name });
    }

    /** DELETE /api/sessions/{id} — 删除任务记录 (级联删对话+遥测) */
    async deleteTask(taskId) {
        return this.delete(`/api/sessions/${encodeURIComponent(taskId)}`);
    }

    /** POST /api/sessions/{id}/activate — 恢复任务 (切换当前会话) */
    async activateTask(taskId) {
        return this.post(`/api/sessions/${encodeURIComponent(taskId)}/activate`);
    }

    /** GET /api/sessions/{id} — 会话详情 (含 task_description/beta_plan/alpha_actions, #11 刷新恢复) */
    async getSessionDetail(sessionId) {
        return this.get(`/api/sessions/${encodeURIComponent(sessionId)}`);
    }

    /** POST /api/sessions/{id}/abort — abort a session */
    async abortSession(sessionId) {
        return this.post(`/api/sessions/${sessionId}/abort`);
    }

    /** GET /api/proposals — get planning proposals */
    async getProposals() {
        return this.get('/api/proposals');
    }

    /** POST /api/proposals/{id}/approve — approve a proposal */
    async approveProposal(proposalId) {
        return this.post(`/api/proposals/${proposalId}/approve`);
    }

    /** POST /api/proposals/{id}/reject — reject a proposal */
    async rejectProposal(proposalId, reason = '') {
        return this.post(`/api/proposals/${proposalId}/reject`, { reason });
    }

    /** GET /api/field/config — field configuration（后端路由为 /field/config） */
    async getFieldConfig() {
        return this.get('/api/field/config');
    }

    // ==========================================================
    // Internal
    // ==========================================================

    /**
     * 统一带超时的 fetch 封装：所有方法（GET/POST/PATCH/DELETE）共享。
     * 超时以 AbortError 抛出，由调用方转为用户可读提示。
     */
    async _fetchWithTimeout(method, path, params = {}, body, timeout) {
        const url = this._buildUrl(path, params);
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), timeout || this.defaultTimeout);
        try {
            const init = {
                method,
                headers: this._headers(),
                signal: controller.signal,
            };
            if (body !== undefined && method !== 'GET' && method !== 'DELETE') {
                init.body = JSON.stringify(body);
            }
            const res = await fetch(url, init);
            return await this._handleResponse(res);
        } finally {
            clearTimeout(timer);
        }
    }

    /**
     * 判断错误是否为请求超时（AbortError）。
     * @param {Error} e
     * @returns {boolean}
     */
    isTimeoutError(e) {
        return !!e && e.name === 'AbortError';
    }

    _buildUrl(path, params = {}) {
        const url = new URL(`${this.baseUrl}${path}`);
        for (const [key, val] of Object.entries(params)) {
            if (val != null && val !== '') {
                url.searchParams.set(key, String(val));
            }
        }
        return url.toString();
    }

    _headers() {
        return {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        };
    }

    async _handleResponse(res) {
        if (!res.ok) {
            let errorDetail;
            try {
                const body = await res.json();
                errorDetail = body.detail || body.message || JSON.stringify(body);
            } catch {
                errorDetail = res.statusText;
            }
            throw new Error(`API ${res.status}: ${errorDetail}`);
        }

        // Handle 204 No Content
        if (res.status === 204) return null;

        const contentType = res.headers.get('content-type') || '';
        if (contentType.includes('application/json')) {
            return res.json();
        }
        return res.text();
    }
}

export { ApiManager };
