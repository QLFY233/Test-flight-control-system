/**
 * DashboardPanel — Single data visualization panel.
 * Renders ECharts charts or value cards based on spec from WS dashboard_config.
 *
 * 2026-08 修复: 移除 mock 假数据 (ALT 28.7m / SPD 1.43 m/s / PROGRESS 47.2% 硬编码 +
 * 时序图随机数)。时序面板 (altitude_line/velocity_line) 订阅 store.drone 实时写入环形缓冲,
 * 增量 setOption 更新图表; value 卡片 (source=altitude|speed|progress) 订阅 store 实时渲染,
 * 无数据时显示 '--'。
 */

import store from '../state.js';
import { esc, escAttr } from '../escape.js';

// 环形缓冲上限: 60s @ 10Hz = 600 点 (对齐 spec 默认 window '60s')
const MAX_POINTS = 600;

class DashboardPanel {
    /**
     * @param {string} panelId - unique panel identifier
     * @param {object} spec - { type, source, window, title, unit?, value? }
     */
    constructor(panelId, spec = {}) {
        this.panelId = panelId;
        this.spec = spec;
        this.container = null;
        this.chart = null;
        this._boundResize = this._resize.bind(this);
        // 具名订阅引用: unmount 时真正解绑, 防泄漏 (对齐 HistoryChart.js 模式)
        this._droneUnsub = null;
        this._flightUnsub = null;
        // 实时数据环形缓冲 (按面板类型只维护需要的)
        this._bufs = {
            altitude: [],   // [ts, z]
            velocity: [[], [], []],  // [ts, vx|vy|vz]
            accel: [[], [], []],     // store 无加速度数据源, 保持空
        };
        this._valueEls = null;  // value 卡片 DOM 引用 (增量刷新用)
    }

    mount(container) {
        this.container = container;
        this._render();
        // 订阅实时数据: drone (pose 10Hz) / flight (status)
        this._droneUnsub = store.subscribe('drone', () => this._onDroneUpdate());
        this._flightUnsub = store.subscribe('flight', () => this._onFlightUpdate());
        // mount 时用当前 store 值立即渲染一次 (页面加载时已有缓存数据)
        this._onDroneUpdate();
        this._onFlightUpdate();
    }

    unmount() {
        if (this._droneUnsub) { this._droneUnsub(); this._droneUnsub = null; }
        if (this._flightUnsub) { this._flightUnsub(); this._flightUnsub = null; }
        if (this.chart && typeof this.chart.dispose === 'function') {
            this.chart.dispose();
        }
        this.chart = null;
        this._valueEls = null;
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
            <div class="dashboard-panel">
                <div class="dashboard-panel__header">
                    <span>${esc(title)}</span>
                    <span style="font-family:var(--font-mono);font-size:var(--text-2xs);color:var(--color-text-disabled);">${esc(this.spec.window || '')}</span>
                </div>
                <div class="dashboard-panel__body" id="dp-body-${escAttr(this.panelId)}"></div>
            </div>
        `;

        const bodyEl = this.container.querySelector(`#dp-body-${CSS.escape(this.panelId)}`);
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

        // accel_line: store 无加速度数据源 → 空图 + 标注, 不显示假数据
        if (this.spec.type === 'accel_line') {
            container.style.position = 'relative';
            const hint = document.createElement('div');
            hint.style.cssText = 'position:absolute;right:8px;bottom:8px;z-index:2;font-family:var(--font-mono);font-size:10px;letter-spacing:0.05em;color:var(--color-text-disabled);background:rgba(10,10,10,0.5);padding:2px 6px;pointer-events:none;';
            hint.textContent = '// 无加速度数据源';
            container.appendChild(hint);
        }
    }

    _buildOption() {
        const type = this.spec.type || 'value';
        const baseOption = {
            backgroundColor: 'transparent',
            grid: { left: '8%', right: '8%', top: '15%', bottom: '15%' },
            textStyle: { color: '#AAAAAA', fontSize: 10 },
            tooltip: { trigger: 'axis' },
        };

        switch (type) {
            case 'altitude_line':
                return {
                    ...baseOption,
                    xAxis: { type: 'time', axisLabel: { color: '#888888', fontSize: 9 } },
                    yAxis: { type: 'value', name: 'ALT (m)', nameTextStyle: { fontSize: 9, color: '#AAAAAA' }, axisLabel: { color: '#888888' }, splitLine: { lineStyle: { color: '#1C1C1C' } } },
                    series: [{
                        type: 'line',
                        data: this._bufs.altitude,
                        symbol: 'none',
                        lineStyle: { color: '#FF2A2A', width: 1.5 },
                        areaStyle: { color: 'rgba(255,42,42,0.08)' },
                    }],
                };
            case 'velocity_line':
                return {
                    ...baseOption,
                    xAxis: { type: 'time', axisLabel: { color: '#888888', fontSize: 9 } },
                    yAxis: { type: 'value', name: 'VEL (m/s)', nameTextStyle: { fontSize: 9, color: '#AAAAAA' }, axisLabel: { color: '#888888' }, splitLine: { lineStyle: { color: '#1C1C1C' } } },
                    series: ['vx', 'vy', 'vz'].map((name, i) => ({
                        type: 'line',
                        name,
                        data: this._bufs.velocity[i],
                        symbol: 'none',
                        lineStyle: { color: ['#FF2A2A', '#4AF626', '#FFB300'][i], width: 1 },
                    })),
                    legend: { textStyle: { color: '#AAAAAA', fontSize: 9 }, itemWidth: 10, itemHeight: 6 },
                };
            case 'accel_line':
                return {
                    ...baseOption,
                    xAxis: { type: 'time', axisLabel: { color: '#888888', fontSize: 9 } },
                    yAxis: { type: 'value', name: 'ACC (m/s²)', nameTextStyle: { fontSize: 9, color: '#AAAAAA' }, axisLabel: { color: '#888888' }, splitLine: { lineStyle: { color: '#1C1C1C' } } },
                    series: ['ax', 'ay', 'az'].map((name, i) => ({
                        type: 'line',
                        name,
                        data: this._bufs.accel[i],
                        symbol: 'none',
                        lineStyle: { color: ['#FF2A2A', '#888', '#FFB300'][i], width: 1 },
                    })),
                    legend: { textStyle: { color: '#888', fontSize: 9 }, itemWidth: 10, itemHeight: 6 },
                };
            case 'bar':
                return {
                    ...baseOption,
                    xAxis: { type: 'category', data: ['异常1', '异常2', '异常3', '异常4', '异常5'], axisLabel: { color: '#888888', fontSize: 9 } },
                    yAxis: { type: 'value', name: '次数', nameTextStyle: { fontSize: 9, color: '#AAAAAA' }, axisLabel: { color: '#888888' }, splitLine: { lineStyle: { color: '#1C1C1C' } } },
                    series: [{ type: 'bar', data: [3, 7, 2, 5, 1], itemStyle: { color: '#FF2A2A' } }],
                };
            default:
                return baseOption;
        }
    }

    /**
     * 实时数据写入: drone (pose 10Hz) 变更回调。
     * 时序面板 → push 环形缓冲 + 增量更新图表; value 卡片 (altitude/speed) → 刷新数值。
     */
    _onDroneUpdate() {
        if (!this.container) return;
        const type = this.spec.type || 'value';
        const drone = store.get('drone') || {};
        const hasPose = drone.timestamp != null;  // null = 从未收到 pose, 视为无数据

        if (type === 'altitude_line') {
            const z = hasPose && drone.position && drone.position.z != null ? drone.position.z : null;
            if (z != null) this._pushLine(this._bufs.altitude, [Date.now(), +z.toFixed(3)]);
        } else if (type === 'velocity_line') {
            const v = hasPose ? drone.velocity : null;
            if (v) {
                const now = Date.now();
                [v.vx, v.vy, v.vz].forEach((val, i) => {
                    if (val != null) this._pushLine(this._bufs.velocity[i], [now, +val.toFixed(3)]);
                });
            }
        } else if (type === 'value' && (this.spec.source === 'altitude' || this.spec.source === 'speed')) {
            this._refreshValueCard();
        }
        // accel_line: store 无加速度数据源 → 保持空图 (已标注)
    }

    /**
     * 实时数据写入: flight (status) 变更回调 → PROGRESS value 卡片刷新。
     */
    _onFlightUpdate() {
        if (!this.container) return;
        const type = this.spec.type || 'value';
        if (type === 'value' && this.spec.source === 'progress') {
            this._refreshValueCard();
        }
    }

    _pushLine(buf, point) {
        buf.push(point);
        if (buf.length > MAX_POINTS) {
            buf.splice(0, buf.length - MAX_POINTS);
        }
        this._updateChart();
    }

    /**
     * 增量更新图表 series.data (merge 模式, 不重建 chart / 不动坐标轴)。
     */
    _updateChart() {
        if (!this.chart || typeof this.chart.isDisposed === 'function' && this.chart.isDisposed()) return;
        const type = this.spec.type;
        let series = null;
        if (type === 'altitude_line') {
            series = [{ data: this._bufs.altitude }];
        } else if (type === 'velocity_line') {
            series = this._bufs.velocity.map(buf => ({ data: buf }));
        } else if (type === 'accel_line') {
            series = this._bufs.accel.map(buf => ({ data: buf }));
        } else {
            return;
        }
        this.chart.setOption({ series }, { lazyUpdate: true });
    }

    _renderValueCard(container) {
        const { value, unit } = this._valueCardData();
        container.innerHTML = `
            <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;padding:var(--space-4);">
                <div class="dashboard-panel__value" data-role="value">${esc(String(value))}</div>
                <div class="dashboard-panel__unit" data-role="unit">${esc(unit)}</div>
            </div>
        `;
        this._valueEls = {
            value: container.querySelector('[data-role="value"]'),
            unit: container.querySelector('[data-role="unit"]'),
        };
        // 显式赋值文本 (与 _refreshValueCard 同源, 不依赖 DOM 解析)
        if (this._valueEls.value) this._valueEls.value.textContent = String(value);
        if (this._valueEls.unit) this._valueEls.unit.textContent = unit;
    }

    /**
     * value 卡片实时取值: source=altitude|speed|progress 读 store; 其余 (如 +ADD PANEL 新建)
     * 用 spec.value 兜底; 无数据一律 '--', 不使用随机数。
     */
    _valueCardData() {
        const source = this.spec.source;
        const drone = store.get('drone') || {};
        const hasPose = drone.timestamp != null;

        if (source === 'altitude') {
            const z = hasPose && drone.position && drone.position.z != null ? drone.position.z : null;
            return { value: z != null ? z.toFixed(2) : '--', unit: this.spec.unit || 'm' };
        }
        if (source === 'speed') {
            const v = hasPose ? drone.velocity : null;
            const speed = v ? Math.hypot(v.vx || 0, v.vy || 0, v.vz || 0) : null;
            return { value: speed != null ? speed.toFixed(2) : '--', unit: this.spec.unit || 'm/s' };
        }
        if (source === 'progress') {
            const p = store.get('flight.progress');
            return { value: p != null ? String(p) : '--', unit: this.spec.unit || '%' };
        }
        // 通用 value 面板 (无 source): spec.value ?? '--'
        return { value: this.spec.value != null ? this.spec.value : '--', unit: this.spec.unit || '' };
    }

    _refreshValueCard() {
        if (!this._valueEls || !this._valueEls.value) return;
        const { value, unit } = this._valueCardData();
        this._valueEls.value.textContent = String(value);
        this._valueEls.unit.textContent = unit;
    }

    _resize() {
        if (this.chart && typeof this.chart.resize === 'function') {
            this.chart.resize();
        }
    }
}

export { DashboardPanel };
