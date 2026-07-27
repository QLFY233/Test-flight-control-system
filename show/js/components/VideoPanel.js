/**
 * VideoPanel — Placeholder for drone video feed.
 * Displays "无信号" (no signal) when no video is available.
 * Future: renders base64 frames onto a canvas.
 */

class VideoPanel {
    constructor() {
        this.container = null;
        this.canvas = null;
        this.ctx = null;
    }

    mount(container) {
        this.container = container;
        container.innerHTML = `
            <div class="view-panel">
                <div class="view-panel__label">视频</div>
                <canvas id="video-canvas" style="display: none; width: 100%; height: 100%;"></canvas>
                <div id="video-no-signal" style="display: flex; align-items: center; justify-content: center; height: 100%; color: var(--color-text-disabled); font-size: var(--font-xl);">
                    无信号
                </div>
            </div>
        `;

        this.canvas = container.querySelector('#video-canvas');
        this.ctx = this.canvas ? this.canvas.getContext('2d') : null;

        // Resize canvas when container changes
        if (this.canvas) {
            this._resizeCanvas();
            const ro = new ResizeObserver(() => this._resizeCanvas());
            ro.observe(container);
        }
    }

    /**
     * Render a base64 frame on the canvas.
     * @param {string} base64 - JPEG/PNG base64 data
     */
    renderFrame(base64) {
        if (!this.canvas || !this.ctx) return;

        const noSignal = this.container.querySelector('#video-no-signal');
        if (noSignal) noSignal.style.display = 'none';
        this.canvas.style.display = 'block';

        const img = new Image();
        img.onload = () => {
            if (!this.ctx) return;
            this._resizeCanvas();
            this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
            this.ctx.drawImage(img, 0, 0, this.canvas.width, this.canvas.height);
        };
        img.src = base64.startsWith('data:') ? base64 : 'data:image/jpeg;base64,' + base64;
    }

    unmount() {
        this.container = null;
        this.canvas = null;
        this.ctx = null;
    }

    _resizeCanvas() {
        if (!this.canvas || !this.container) return;
        const rect = this.container.getBoundingClientRect();
        this.canvas.width = rect.width;
        this.canvas.height = rect.height;
    }
}

export { VideoPanel };
