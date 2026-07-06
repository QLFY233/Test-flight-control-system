/**
 * REST API Client — Typed HTTP methods with error handling.
 */

class ApiManager {
    constructor(baseUrl = 'http://localhost:8000') {
        this.baseUrl = baseUrl.replace(/\/+$/, '');
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
     * @returns {Promise<any>}
     */
    async get(path, params = {}) {
        const url = this._buildUrl(path, params);
        const res = await fetch(url, {
            method: 'GET',
            headers: this._headers(),
        });
        return this._handleResponse(res);
    }

    /**
     * POST request.
     * @param {string} path
     * @param {object} [body]
     * @returns {Promise<any>}
     */
    async post(path, body = {}) {
        const url = this._buildUrl(path);
        const res = await fetch(url, {
            method: 'POST',
            headers: this._headers(),
            body: JSON.stringify(body),
        });
        return this._handleResponse(res);
    }

    /**
     * PATCH request.
     * @param {string} path
     * @param {object} [body]
     * @returns {Promise<any>}
     */
    async patch(path, body = {}) {
        const url = this._buildUrl(path);
        const res = await fetch(url, {
            method: 'PATCH',
            headers: this._headers(),
            body: JSON.stringify(body),
        });
        return this._handleResponse(res);
    }

    /**
     * DELETE request.
     * @param {string} path
     * @returns {Promise<any>}
     */
    async delete(path) {
        const url = this._buildUrl(path);
        const res = await fetch(url, {
            method: 'DELETE',
            headers: this._headers(),
        });
        return this._handleResponse(res);
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

    /** GET /api/telemetry — current telemetry snapshot */
    async getTelemetry() {
        return this.get('/api/telemetry');
    }

    /** GET /api/conversations — chat history */
    async getConversations(sessionId) {
        return this.get('/api/conversations', { session_id: sessionId });
    }

    /** GET /api/environments — saved environments */
    async getEnvironments() {
        return this.get('/api/environments');
    }

    /** POST /api/environments — save an environment preset */
    async saveEnvironment(env) {
        return this.post('/api/environments', env);
    }

    /** GET /api/pose — current drone pose */
    async getCurrentPose() {
        return this.get('/api/pose');
    }

    /** POST /api/sessions — create a new flight session */
    async createSession(config) {
        return this.post('/api/sessions', config);
    }

    /** POST /api/sessions/{id}/abort — abort a session */
    async abortSession(sessionId) {
        return this.post(`/api/sessions/${sessionId}/abort`);
    }

    /** GET /api/proposals — get planning proposals */
    async getProposals(sessionId) {
        return this.get('/api/proposals', { session_id: sessionId });
    }

    /** POST /api/proposals/{id}/approve — approve a proposal */
    async approveProposal(proposalId) {
        return this.post(`/api/proposals/${proposalId}/approve`);
    }

    /** POST /api/proposals/{id}/reject — reject a proposal */
    async rejectProposal(proposalId, reason = '') {
        return this.post(`/api/proposals/${proposalId}/reject`, { reason });
    }

    /** GET /api/field — field configuration */
    async getFieldConfig() {
        return this.get('/api/field');
    }

    // ==========================================================
    // Internal
    // ==========================================================

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
