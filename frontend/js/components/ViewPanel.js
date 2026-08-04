/**
 * ViewPanel — Container that renders Scene3D, VideoPanel, or ECharts charts based on source prop.
 * Receives a slot index and source type. Creates and manages lifecycle of the inner component.
 */

import { VideoPanel } from './VideoPanel.js';
import { AltitudeChart } from '../charts/AltitudeChart.js';
import { VelocityChart } from '../charts/VelocityChart.js';
import { FieldMap2D } from '../charts/FieldMap2D.js';
import { HistoryChart } from '../charts/HistoryChart.js';
import { Scene3D } from '../charts/Scene3D.js';
import store from '../state.js';

class ViewPanel {
    /**
     * @param {number} slotIndex - 0-based slot index
     * @param {string} source - '3d' | 'video' | 'chart'
     * @param {string} [chartType] - for 'chart' source: 'altitude' | 'velocity' | 'fieldmap' | 'history'
     */
    constructor(slotIndex, source, chartType = 'altitude') {
        this.slotIndex = slotIndex;
        this.source = source;
        this.chartType = chartType;
        this.container = null;
        this.innerComponent = null;
    }

    mount(container) {
        this.container = container;
        container.innerHTML = '';

        const wrapper = document.createElement('div');
        wrapper.className = 'view-panel';
        wrapper.style.width = '100%';
        wrapper.style.height = '100%';

        // Drag handle / label (仅标题栏可拖拽, 避免与 Scene3D OrbitControls 鼠标事件冲突)
        const label = document.createElement('div');
        label.className = 'view-panel__label';
        label.textContent = this._getLabel();
        label.draggable = true;
        label.title = '拖动交换视图';
        wrapper.appendChild(label);

        const innerContainer = document.createElement('div');
        innerContainer.style.width = '100%';
        innerContainer.style.height = '100%';
        wrapper.appendChild(innerContainer);

        container.appendChild(wrapper);

        // Drag events (P4: drag-and-drop swap) — 句柄在标题栏, 落点在整个面板
        label.addEventListener('dragstart', (e) => {
            e.dataTransfer.setData('text/plain', String(this.slotIndex));
            wrapper.style.opacity = '0.4';
            wrapper.classList.add('view-panel--dragging');
        });
        label.addEventListener('dragend', () => {
            wrapper.style.opacity = '1';
            wrapper.classList.remove('view-panel--dragging');
            document.querySelectorAll('.view-panel--drop-target').forEach(el => el.classList.remove('view-panel--drop-target'));
        });
        wrapper.addEventListener('dragover', (e) => {
            e.preventDefault();
            wrapper.classList.add('view-panel--drop-target');
        });
        wrapper.addEventListener('dragleave', () => {
            wrapper.classList.remove('view-panel--drop-target');
        });
        wrapper.addEventListener('drop', (e) => {
            e.preventDefault();
            wrapper.classList.remove('view-panel--drop-target');
            const fromIdx = parseInt(e.dataTransfer.getData('text/plain'));
            const toIdx = this.slotIndex;
            if (fromIdx >= 0 && fromIdx !== toIdx) {
                // Swap sources in store
                this._swapViewSources(fromIdx, toIdx);
            }
        });

        this._createInner(innerContainer);
    }

    /**
     * Swap view sources between two slots and emit event for re-render.
     */
    _swapViewSources(fromIdx, toIdx) {
        import('../state.js').then(mod => {
            const store = mod.default;
            const sources = [...(store.get('ui.viewSources') || ['chart'])];
            const temp = sources[fromIdx];
            sources[fromIdx] = sources[toIdx];
            sources[toIdx] = temp;
            store.set('ui.viewSources', sources);
            // Re-render via event
            import('../event-bus.js').then(b => {
                b.default.emit('view-source-swapped', { fromIdx, toIdx, sources });
            });
        });
    }

    _createInner(innerContainer) {
        switch (this.source) {
            case 'video':
                this.innerComponent = new VideoPanel();
                this.innerComponent.mount(innerContainer);
                break;
            case '3d':
                this.innerComponent = new Scene3D();
                this.innerComponent.mount(innerContainer);
                break;
            case 'chart':
                this._mountChart(innerContainer);
                break;
            default:
                innerContainer.innerHTML = `<div style="display: flex; align-items: center; justify-content: center; height: 100%; color: var(--color-text-disabled);">未知源</div>`;
                break;
        }
    }

    _mountChart(container) {
        switch (this.chartType) {
            case 'altitude':
                this.innerComponent = new AltitudeChart();
                break;
            case 'velocity':
                this.innerComponent = new VelocityChart();
                break;
            case 'fieldmap':
                this.innerComponent = new FieldMap2D();
                break;
            case 'history':
                this.innerComponent = new HistoryChart();
                break;
            default:
                this.innerComponent = new AltitudeChart();
                break;
        }
        if (this.innerComponent && this.innerComponent.mount) {
            this.innerComponent.mount(container);
        }
    }

    /**
     * Switch the source type and re-render.
     */
    setSource(source, chartType) {
        if (this.source === source && this.chartType === chartType) return;
        this.source = source;
        this.chartType = chartType || 'altitude';
        if (this.container) {
            this._unmountInner();
            this.mount(this.container);
        }
    }

    _getLabel() {
        switch (this.source) {
            case 'video': return '视频';
            case '3d': return '3D 视图';
            case 'chart': {
                const labels = { altitude: '高度图', velocity: '速度图', fieldmap: '场地俯视图', history: '历史回放' };
                return labels[this.chartType] || '图表';
            }
            default: return this.source;
        }
    }

    _unmountInner() {
        if (this.innerComponent && this.innerComponent.unmount) {
            this.innerComponent.unmount();
        }
        this.innerComponent = null;
    }

    unmount() {
        this._unmountInner();
        this.container = null;
    }
}

export { ViewPanel };
