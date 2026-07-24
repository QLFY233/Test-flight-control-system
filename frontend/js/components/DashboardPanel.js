/**
 * DashboardPanel — Single data visualization panel.
 * Renders ECharts charts or value cards based on spec from WS dashboard_config.
 * Subscribes to WS 'dashboard_config' for updates.
 */

class DashboardPanel {
    /**
     * @param {string} panelId - unique panel identifier
     * @param {object} spec - { type, source, window, title }
     */
    constructor(panelId, spec = {}) {
        this.panelId = panelId;
        this.spec = spec;
        this.container = null;
        this.chart = null;
        this._boundResize = this._resize.bind(this);
    }

    mount(container) {
        this.container = container;
        this._render();
    }

    unmount() {
        if (this.chart && typeof this.chart.dispose === 'function') {
            this.chart.dispose();
        }
        this.chart = null;
        this.container = null;
        window.removeEventListener('resize', this._boundResize);
    }

    /**
     * Update panel with new spec (from WS dashboard_config).
     * @param {object} spec - { type, source, window, title, filter? }
     */
    updateSpec(spec) {
        this.spec = { ...this.spec, ...spec };
        if (this.container) {
            this._render();
        }
    }

    _render() {
        if (!this.container) return;

        const title = this.spec.title || this.spec.type || '面板';
        this.container.innerHTML = `
            <div class="dashboard-panel" style="width: 100%; height: 100%; display: flex; flex-direction: column;">
                <div class="dashboard-panel__header" style="padding: 4px 8px; font-size: var(--font-xs); color: var(--color-text-secondary); border-bottom: 1px solid var(--color-border); display: flex; justify-content: space-between; align-items: center;">
                    <span>${title}</span>
                    <span style="font-size: 10px; color: var(--color-text-disabled);">${this.spec.window || ''}</span>
                </div>
                <div class="dashboard-panel__body" style="flex: 1; min-height: 0;" id="dp-body-${this.panelId}"></div>
            </div>
        `;

        const bodyEl = this.container.querySelector(`#dp-body-${this.panelId}`);
        if (!bodyEl) return;

        this._renderContent(bodyEl);
        window.addEventListener('resize', this._boundResize);
    }

    _renderContent(bodyEl) {
        const type = this.spec.type || 'value';

        switch (type) {
            case 'altitude_line':
            case 'velocity_line':
            case 'accel_line':
            case 'multi_line':
                this._renderEChart(bodyEl);
                break;
            case 'bar':
                this._renderEChart(bodyEl);
                break;
            case 'value':
            default:
                this._renderValueCard(bodyEl);
                break;
        }
    }

    _renderEChart(container) {
        if (typeof echarts === 'undefined') {
            container.innerHTML = '<div style="padding: var(--space-md); color: var(--color-text-disabled); text-align: center;">ECharts 未加载</div>';
            return;
        }

        if (this.chart) {
            this.chart.dispose();
        }

        this.chart = echarts.init(container);
        const option = this._buildOption();
        this.chart.setOption(option);
    }

    _buildOption() {
        const type = this.spec.type || 'value';
        const baseOption = {
            backgroundColor: 'transparent',
            grid: { left: '8%', right: '8%', top: '15%', bottom: '15%' },
            textStyle: { color: '#9E9E9E', fontSize: 10 },
            tooltip: { trigger: 'axis' },
        };

        switch (type) {
            case 'altitude_line':
                return {
                    ...baseOption,
                    xAxis: { type: 'time', axisLabel: { color: '#616161', fontSize: 9 } },
                    yAxis: { type: 'value', name: '高度 (m)', nameTextStyle: { fontSize: 9 }, axisLabel: { color: '#616161' }, splitLine: { lineStyle: { color: '#1A1A1A' } } },
                    series: [{
                        type: 'line',
                        data: this._mockData(20, 0.5, 3.0),
                        symbol: 'none',
                        lineStyle: { color: '#00BCD4', width: 1.5 },
                        areaStyle: { color: 'rgba(0,188,212,0.1)' },
                    }],
                };
            case 'velocity_line':
                return {
                    ...baseOption,
                    xAxis: { type: 'time', axisLabel: { color: '#616161', fontSize: 9 } },
                    yAxis: { type: 'value', name: '速度 (m/s)', nameTextStyle: { fontSize: 9 }, axisLabel: { color: '#616161' }, splitLine: { lineStyle: { color: '#1A1A1A' } } },
                    series: ['vx', 'vy', 'vz'].map((name, i) => ({
                        type: 'line',
                        name,
                        data: this._mockData(20, -1.0, 1.0),
                        symbol: 'none',
                        lineStyle: { color: ['#00BCD4', '#4CAF50', '#FFC107'][i], width: 1 },
                    })),
                    legend: { textStyle: { color: '#9E9E9E', fontSize: 9 }, itemWidth: 10, itemHeight: 6 },
                };
            case 'accel_line':
                return {
                    ...baseOption,
                    xAxis: { type: 'time', axisLabel: { color: '#616161', fontSize: 9 } },
                    yAxis: { type: 'value', name: '加速度 (m/s²)', nameTextStyle: { fontSize: 9 }, axisLabel: { color: '#616161' }, splitLine: { lineStyle: { color: '#1A1A1A' } } },
                    series: ['ax', 'ay', 'az'].map((name, i) => ({
                        type: 'line',
                        name,
                        data: this._mockData(20, -0.5, 0.5),
                        symbol: 'none',
                        lineStyle: { color: ['#F44336', '#E040FB', '#00BCD4'][i], width: 1 },
                    })),
                    legend: { textStyle: { color: '#9E9E9E', fontSize: 9 }, itemWidth: 10, itemHeight: 6 },
                };
            case 'bar':
                return {
                    ...baseOption,
                    xAxis: { type: 'category', data: ['异常1', '异常2', '异常3', '异常4', '异常5'], axisLabel: { color: '#616161', fontSize: 9 } },
                    yAxis: { type: 'value', name: '次数', nameTextStyle: { fontSize: 9 }, axisLabel: { color: '#616161' }, splitLine: { lineStyle: { color: '#1A1A1A' } } },
                    series: [{ type: 'bar', data: [3, 7, 2, 5, 1], itemStyle: { color: '#FFC107' } }],
                };
            default:
                return baseOption;
        }
    }

    _renderValueCard(container) {
        const value = this.spec.value ?? Math.round(Math.random() * 100) / 10;
        const unit = this.spec.unit || '';
        container.innerHTML = `
            <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; padding: var(--space-md);">
                <div style="font-size: var(--font-2xl); font-weight: 300; color: var(--color-cyan);">${value}</div>
                <div style="font-size: var(--font-xs); color: var(--color-text-disabled); margin-top: 4px;">${unit}</div>
            </div>
        `;
    }

    _mockData(count, min, max) {
        const now = Date.now();
        const data = [];
        for (let i = 0; i < count; i++) {
            data.push([now - (count - i) * 1000, +(min + Math.random() * (max - min)).toFixed(2)]);
        }
        return data;
    }

    _resize() {
        if (this.chart && typeof this.chart.resize === 'function') {
            this.chart.resize();
        }
    }
}

export { DashboardPanel };
