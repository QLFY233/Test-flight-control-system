/**
 * AltitudeChart — Real-time altitude time series (ECharts line chart).
 * Max 300 data points, auto Y-axis, dark theme.
 */

import store from '../state.js';

class AltitudeChart {
    constructor() {
        this.chart = null;
        this.container = null;
        this.data = [];
        this.maxPoints = 300;
        this._unsubscribe = null;
    }

    mount(container) {
        this.container = container;

        // Create chart container
        const chartEl = document.createElement('div');
        chartEl.style.width = '100%';
        chartEl.style.height = '100%';
        container.appendChild(chartEl);

        this.chart = echarts.init(chartEl, null, {
            backgroundColor: 'transparent',
        });

        this.chart.setOption(this._getOption());

        // Subscribe to drone position
        this._unsubscribe = store.subscribe('drone.position', (pos) => {
            if (!pos) return;
            const t = new Date().toLocaleTimeString('zh-CN', { hour12: false });
            this.data.push({
                time: t,
                value: pos.z != null ? pos.z : pos.y,
            });
            if (this.data.length > this.maxPoints) {
                this.data = this.data.slice(-this.maxPoints);
            }
            this._update();
        });

        // Handle resize
        this._resizeHandler = () => this.chart && this.chart.resize();
        window.addEventListener('resize', this._resizeHandler);
    }

    unmount() {
        if (this._unsubscribe) {
            this._unsubscribe();
            this._unsubscribe = null;
        }
        if (this._resizeHandler) {
            window.removeEventListener('resize', this._resizeHandler);
            this._resizeHandler = null;
        }
        if (this.chart) {
            this.chart.dispose();
            this.chart = null;
        }
        if (this.container) {
            this.container.innerHTML = '';
            this.container = null;
        }
    }

    _getOption() {
        return {
            darkMode: true,
            backgroundColor: 'transparent',
            grid: {
                top: 40,
                right: 20,
                bottom: 30,
                left: 50,
            },
            title: {
                text: '高度',
                left: 'center',
                top: 8,
                textStyle: {
                    color: '#9E9E9E',
                    fontSize: 12,
                    fontWeight: 'normal',
                },
            },
            xAxis: {
                type: 'category',
                data: [],
                axisLine: { lineStyle: { color: '#2A2A2A' } },
                axisTick: { show: false },
                axisLabel: { color: '#616161', fontSize: 10 },
                splitLine: { show: false },
            },
            yAxis: {
                type: 'value',
                name: 'm',
                nameTextStyle: { color: '#616161', fontSize: 10 },
                axisLine: { lineStyle: { color: '#2A2A2A' } },
                axisLabel: { color: '#616161', fontSize: 10 },
                splitLine: { lineStyle: { color: '#1A1A1A' } },
            },
            series: [{
                name: 'Altitude',
                type: 'line',
                data: [],
                smooth: true,
                showSymbol: false,
                lineStyle: { color: '#00BCD4', width: 2 },
                areaStyle: {
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                        { offset: 0, color: 'rgba(0, 188, 212, 0.3)' },
                        { offset: 1, color: 'rgba(0, 188, 212, 0.02)' },
                    ]),
                },
            }],
            animation: true,
            animationDuration: 300,
        };
    }

    _update() {
        if (!this.chart || this.chart.isDisposed()) return;

        this.chart.setOption({
            xAxis: {
                data: this.data.map(d => d.time),
            },
            series: [{
                data: this.data.map(d => d.value),
            }],
        });
    }
}

export { AltitudeChart };
