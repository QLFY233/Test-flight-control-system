/**
 * SettingsPage — Configuration page with tabs.
 * Backend, Display, Voice, Environment settings + JSON preview.
 * Saves to localStorage.
 */

import store from '../state.js';
import bus from '../event-bus.js';
import { config, apiManager } from '../app.js';
import { deepMerge } from '../config.js';

class SettingsPage {
    constructor() {
        this.container = null;
        this.title = '设置';
        this.activeTab = 'backend';
        this.localConfig = {};
    }

    mount(container) {
        this.container = container;
        this._initLocalConfig();
        this.render();
    }

    unmount() {
        this.container = null;
    }

    _initLocalConfig() {
        try {
            this.localConfig = JSON.parse(localStorage.getItem('flight-control-config') || '{}');
        } catch {
            this.localConfig = {};
        }
    }

    render() {
        const tabs = ['backend', 'display', 'voice', 'environment'];
        const tabLabels = { backend: '后端', display: '显示', voice: '语音', environment: '环境' };

        const bc = this.localConfig.backend || {};
        const dc = this.localConfig.display || {};
        const vc = this.localConfig.voice || {};
        const ec = this.localConfig.environment || {};

        let bodyHtml = '';
        switch (this.activeTab) {
            case 'backend':
                bodyHtml = `
                    <div class="settings-page__section-title">后端连接</div>
                    <div class="settings-page__field">
                        <label class="input-group__label">Base URL</label>
                        <input type="text" class="input" id="cfg-backend-url" value="${this._escAttr(bc.base_url || 'http://localhost:8000')}" placeholder="http://localhost:8000">
                    </div>
                    <div class="settings-page__field">
                        <label class="input-group__label">WebSocket Endpoint</label>
                        <input type="text" class="input" id="cfg-backend-ws" value="${this._escAttr(bc.ws_endpoint || '/ws')}" placeholder="/ws">
                    </div>
                    <div class="settings-page__field">
                        <label class="input-group__label">SSE Beta Endpoint</label>
                        <input type="text" class="input" id="cfg-backend-sse" value="${this._escAttr(bc.sse_beta || '/api/chat/beta')}" placeholder="/api/chat/beta">
                    </div>
                `;
                break;

            case 'display':
                bodyHtml = `
                    <div class="settings-page__section-title">显示设置</div>
                    <div class="settings-page__field settings-page__field--inline">
                        <span class="input-group__label">主题</span>
                        <select class="input" id="cfg-display-theme" style="width: auto;">
                            <option value="dark" ${dc.theme === 'dark' ? 'selected' : ''}>暗色</option>
                            <option value="light" ${dc.theme === 'light' ? 'selected' : ''}>亮色</option>
                        </select>
                    </div>
                    <div class="settings-page__field settings-page__field--inline">
                        <span class="input-group__label">语言</span>
                        <select class="input" id="cfg-display-lang" style="width: auto;">
                            <option value="zh-CN" ${dc.language === 'zh-CN' ? 'selected' : ''}>中文</option>
                            <option value="en" ${dc.language === 'en' ? 'selected' : ''}>English</option>
                        </select>
                    </div>
                `;
                break;

            case 'voice':
                bodyHtml = `
                    <div class="settings-page__section-title">语音设置</div>
                    <div class="settings-page__field settings-page__field--inline">
                        <span class="input-group__label">发送后自动语音播报</span>
                        <div class="settings-page__toggle ${vc.autoTts ? 'settings-page__toggle--on' : ''}" id="cfg-voice-autotts"></div>
                    </div>
                    <div class="settings-page__field settings-page__field--inline">
                        <span class="input-group__label">语音输入 (STT)</span>
                        <div class="settings-page__toggle ${vc.sttEnabled !== false ? 'settings-page__toggle--on' : ''}" id="cfg-voice-stt"></div>
                    </div>
                    <div class="settings-page__field settings-page__field--inline">
                        <span class="input-group__label">语音输出 (TTS)</span>
                        <div class="settings-page__toggle ${vc.ttsEnabled !== false ? 'settings-page__toggle--on' : ''}" id="cfg-voice-tts"></div>
                    </div>
                `;
                break;

            case 'environment':
                const envStore = store.get('environment');
                bodyHtml = `
                    <div class="settings-page__section-title">环境参数</div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-md);">
                        <div class="settings-page__field">
                            <label class="input-group__label">温度 (°C)</label>
                            <input type="number" class="input" id="cfg-env-temp" value="${envStore.temperature ?? 25}" step="0.1">
                        </div>
                        <div class="settings-page__field">
                            <label class="input-group__label">湿度 (%)</label>
                            <input type="number" class="input" id="cfg-env-humidity" value="${envStore.humidity ?? 60}" min="0" max="100">
                        </div>
                        <div class="settings-page__field">
                            <label class="input-group__label">风速 (m/s)</label>
                            <input type="number" class="input" id="cfg-env-wind-speed" value="${envStore.windSpeed ?? 0}" step="0.1" min="0">
                        </div>
                        <div class="settings-page__field">
                            <label class="input-group__label">风向 (°)</label>
                            <input type="number" class="input" id="cfg-env-wind-dir" value="${envStore.windDirection ?? 0}" min="0" max="360">
                        </div>
                        <div class="settings-page__field">
                            <label class="input-group__label">气压 (hPa)</label>
                            <input type="number" class="input" id="cfg-env-pressure" value="${envStore.pressure ?? 1013}" step="0.1">
                        </div>
                        <div class="settings-page__field">
                            <label class="input-group__label">地点</label>
                            <input type="text" class="input" id="cfg-env-location" value="${this._escAttr(envStore.location || '')}" placeholder="地点描述">
                        </div>
                    </div>
                    <div style="margin-top: var(--space-md); display: flex; gap: var(--space-sm);">
                        <button class="btn btn--secondary btn--sm" id="btn-env-apply">应用环境参数</button>
                        <button class="btn btn--ghost btn--sm" id="btn-env-preset-indoor">室内预设</button>
                        <button class="btn btn--ghost btn--sm" id="btn-env-preset-outdoor">室外预设</button>
                    </div>
                `;
                break;
        }

        this.container.innerHTML = `
            <div class="settings-page">
                <div class="tabs settings-page__tabs">
                    ${tabs.map(t => `
                        <div class="tabs__tab ${this.activeTab === t ? 'tabs__tab--active' : ''}" data-tab="${t}">
                            ${tabLabels[t]}
                        </div>
                    `).join('')}
                </div>
                <div class="settings-page__body" id="settings-body">
                    ${bodyHtml}

                    <div class="settings-page__section-title">配置预览 (JSON)</div>
                    <textarea class="settings-page__json-preview" id="cfg-json-preview" readonly>${this._getConfigPreview()}</textarea>

                    <div style="display: flex; gap: var(--space-sm);">
                        <button class="btn btn--primary" id="btn-save-settings">保存设置</button>
                        <button class="btn btn--ghost" id="btn-reset-settings">恢复默认</button>
                    </div>
                </div>
            </div>
        `;

        // Tab clicks
        this.container.querySelectorAll('.tabs__tab').forEach(tab => {
            tab.addEventListener('click', () => {
                this.activeTab = tab.dataset.tab;
                this.render();
            });
        });

        // Voice toggles
        this._bindToggles();

        // Save
        this.container.querySelector('#btn-save-settings')?.addEventListener('click', () => this._saveSettings());
        this.container.querySelector('#btn-reset-settings')?.addEventListener('click', () => this._resetSettings());

        // Environment buttons
        this.container.querySelector('#btn-env-apply')?.addEventListener('click', () => this._applyEnvironment());
        this.container.querySelector('#btn-env-preset-indoor')?.addEventListener('click', () => this._presetEnvironment('indoor'));
        this.container.querySelector('#btn-env-preset-outdoor')?.addEventListener('click', () => this._presetEnvironment('outdoor'));
    }

    _bindToggles() {
        const toggles = [
            { id: 'cfg-voice-autotts', key: 'voice.autoTts' },
            { id: 'cfg-voice-stt', key: 'voice.sttEnabled' },
            { id: 'cfg-voice-tts', key: 'voice.ttsEnabled' },
        ];

        for (const { id, key } of toggles) {
            const el = this.container?.querySelector(`#${id}`);
            if (!el) continue;
            el.addEventListener('click', () => {
                const current = this._getLocalConfigValue(key);
                this._setLocalConfigValue(key, !current);
                el.classList.toggle('settings-page__toggle--on', !current);
                this._updateJsonPreview();
            });
        }
    }

    _getLocalConfigValue(path) {
        const keys = path.split('.');
        let v = this.localConfig;
        for (const k of keys) {
            if (v == null) return undefined;
            v = v[k];
        }
        return v;
    }

    _setLocalConfigValue(path, value) {
        const keys = path.split('.');
        let current = this.localConfig;
        for (let i = 0; i < keys.length - 1; i++) {
            if (!current[keys[i]]) current[keys[i]] = {};
            current = current[keys[i]];
        }
        current[keys[keys.length - 1]] = value;
    }

    _saveSettings() {
        // Read backend fields
        const backend = {
            base_url: this._getInputVal('cfg-backend-url'),
            ws_endpoint: this._getInputVal('cfg-backend-ws'),
            sse_beta: this._getInputVal('cfg-backend-sse'),
        };
        if (backend.base_url) this.localConfig.backend = { ...(this.localConfig.backend || {}), ...backend };

        // Read display
        const theme = this._getSelectVal('cfg-display-theme');
        const lang = this._getSelectVal('cfg-display-lang');
        if (theme || lang) this.localConfig.display = { ...(this.localConfig.display || {}), theme, language: lang };

        localStorage.setItem('flight-control-config', JSON.stringify(this.localConfig));

        // Update API base URL if changed
        if (backend.base_url) {
            apiManager.setBaseUrl(backend.base_url);
        }

        alert('设置已保存');
    }

    _resetSettings() {
        if (!confirm('确定要恢复所有设置为默认值吗？')) return;
        localStorage.removeItem('flight-control-config');
        this.localConfig = {};
        this.render();
    }

    _applyEnvironment() {
        const env = {
            temperature: parseFloat(this._getInputVal('cfg-env-temp')) || 25,
            humidity: parseFloat(this._getInputVal('cfg-env-humidity')) || 60,
            windSpeed: parseFloat(this._getInputVal('cfg-env-wind-speed')) || 0,
            windDirection: parseFloat(this._getInputVal('cfg-env-wind-dir')) || 0,
            pressure: parseFloat(this._getInputVal('cfg-env-pressure')) || 1013,
            location: this._getInputVal('cfg-env-location') || '',
        };
        store.batch(() => {
            for (const [key, val] of Object.entries(env)) {
                store.set(`environment.${key}`, val);
            }
        });
        alert('环境参数已应用');
    }

    _presetEnvironment(preset) {
        const presets = {
            indoor: { temperature: 22, humidity: 50, windSpeed: 0, windDirection: 0, pressure: 1013, location: '室内测试场' },
            outdoor: { temperature: 28, humidity: 65, windSpeed: 3, windDirection: 180, pressure: 1010, location: '室外飞行场' },
        };
        const p = presets[preset];
        if (!p) return;

        store.batch(() => {
            for (const [key, val] of Object.entries(p)) {
                store.set(`environment.${key}`, val);
            }
        });
        this.render();
    }

    _getInputVal(id) {
        return this.container?.querySelector(`#${id}`)?.value || '';
    }

    _getSelectVal(id) {
        return this.container?.querySelector(`#${id}`)?.value || '';
    }

    _getConfigPreview() {
        try {
            const saved = JSON.parse(localStorage.getItem('flight-control-config') || '{}');
            return JSON.stringify(saved, null, 2);
        } catch {
            return '{}';
        }
    }

    _updateJsonPreview() {
        const el = this.container?.querySelector('#cfg-json-preview');
        if (el) el.value = this._getConfigPreview();
    }

    _escAttr(str) {
        return String(str || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }
}

export { SettingsPage };
