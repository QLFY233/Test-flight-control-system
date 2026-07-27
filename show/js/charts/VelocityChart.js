/**
 * VelocityChart — Real-time velocity 3-line chart (vx, vy, vz).
 * Dark theme, auto range.
 */

import store from '../state.js';

class VelocityChart {
    constructor() {
        this.chart = null;
        this.container = null;
        this.data = [];
        this.maxPoints = 300;
        this._unsubscribe = null;
    }

    mount(container) {
        this.container = container;

        const chartEl = document.createElement('div');
        chartEl.style.width = '100%';
        chartEl.style.height = '100%';
        container.appendChild(chartEl);

        this.chart = echarts.init(chartEl, null, {
            backgroundColor: 'transparent',
        });

        this.chart.setOption(this._getOption());

        // Subscribe to velocity
        this._unsubscribe = store.subscribe('drone.velocity', (vel) => {
            if (!vel) return;
            const t = new Date().toLocaleTimeString('zh-CN', { hour12: false });
            this.data.push({
                time: t,
                vx: vel.vx || 0,
                vy: vel.vy || 0,
                vz: vel.vz || 0,
            });
            if (this.data.length > this.maxPoints) {
                this.data = this.data.slice(-this.maxPoints);
            }
            this._update();
        });

        window.addEventListener('resize', this._resizeHandler = () => {
            this.chart && this.chart.resize();
        });
    }

    unmount() {
        if (this._unsubscribe) { this._unsubscribe(); this._unsubscribe = null; }
        if (this._resizeHandler) { window.removeEventListener('resize', this._resizeHandler); this._resizeHandler = null; }
        if (this.chart) { this.chart.dispose(); this.chart = null; }
        if (this.container) { this.container.innerHTML = ''; this.container = null; }
    }

    _getOption() {
        return {
            darkMode: true,
            backgroundColor: 'transparent',
            tooltip: {
                trigger: 'axis',
            },
            legend: {
                data: ['Vx', 'Vy', 'Vz'],
                top: 4,
                textStyle: { color: '#9E9E9E', fontSize: 10 },
            },
            grid: {
                top: 40,
                right: 20,
                bottom: 30,
                left: 50,
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
                name: 'm/s',
                nameTextStyle: { color: '#616161', fontSize: 10 },
                axisLine: { lineStyle: { color: '#2A2A2A' } },
                axisLabel: { color: '#616161', fontSize: 10 },
                splitLine: { lineStyle: { color: '#1A1A1A' } },
            },
            series: [
                {
                    name: 'Vx',
                    type: 'line',
                    data: [],
                    smooth: true,
                    showSymbol: false,
                    lineStyle: { color: '#F44336', width: 1.5 },
                },
                {
                    name: 'Vy',
                    type: 'line',
                    data: [],
                    smooth: true,
                    showSymbol: false,
                    lineStyle: { color: '#4CAF50', width: 1.5 },
                },
                {
                    name: 'Vz',
                    type: 'line',
                    data: [],
                    smooth: true,
                    showSymbol: false,
                    lineStyle: { color: '#2196F3', width: 1.5 },
                },
            ],
            animation: true,
            animationDuration: 300,
        };
    }

    _update() {
        if (!this.chart || this.chart.isDisposed()) return;

        this.chart.setOption({
            xAxis: { data: this.data.map(d => d.time) },
            series: [
                { data: this.data.map(d => d.vx) },
                { data: this.data.map(d => d.vy) },
                { data: this.data.map(d => d.vz) },
            ],
        });
    }
}

export { VelocityChart };
