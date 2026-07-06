/**
 * Scene3D — Three.js scene manager.
 * Uses global THREE from CDN.
 * Coordinate convention: field (x, y, z) -> Three.js (x, z, y) — Y-up in Three.js.
 */

class Scene3D {
    constructor() {
        this.scene = null;
        this.camera = null;
        this.renderer = null;
        this.controls = null;
        this.animationId = null;
        this.container = null;
        this.paused = false;
        this.renderCallbacks = [];

        // Build the scene
        this._init();
    }

    _init() {
        // Scene
        this.scene = new THREE.Scene();
        this.scene.background = new THREE.Color(0x0a0a0a);
        this.scene.fog = new THREE.Fog(0x0a0a0a, 50, 200);

        // Camera
        this.camera = new THREE.PerspectiveCamera(
            60, // FOV
            1,  // aspect (updated on mount)
            0.1,
            500
        );
        this.camera.position.set(30, 40, 30);
        this.camera.lookAt(0, 0, 5);

        // Renderer
        this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
        this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        this.renderer.shadowMap.enabled = true;
        this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
        this.renderer.outputColorSpace = THREE.SRGBColorSpace;

        // Lights
        const ambient = new THREE.AmbientLight(0x404040, 0.6);
        this.scene.add(ambient);

        const dirLight = new THREE.DirectionalLight(0xffffff, 1.2);
        dirLight.position.set(50, 80, 50);
        dirLight.castShadow = true;
        dirLight.shadow.mapSize.width = 1024;
        dirLight.shadow.mapSize.height = 1024;
        dirLight.shadow.camera.near = 0.5;
        dirLight.shadow.camera.far = 300;
        dirLight.shadow.camera.left = -100;
        dirLight.shadow.camera.right = 100;
        dirLight.shadow.camera.top = 100;
        dirLight.shadow.camera.bottom = -100;
        this.scene.add(dirLight);

        // Controls (OrbitControls)
        if (THREE.OrbitControls) {
            this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
            this.controls.enableDamping = true;
            this.controls.dampingFactor = 0.1;
            this.controls.minDistance = 5;
            this.controls.maxDistance = 200;
            this.controls.target.set(0, 0, 10);
            this.controls.update();
        }
    }

    /**
     * Mount the 3D scene into a DOM container.
     * @param {HTMLElement} container
     */
    mount(container) {
        if (this.container === container) return;

        // Unmount from previous container
        if (this.container) {
            this.unmount();
        }

        this.container = container;
        container.appendChild(this.renderer.domElement);

        this._resize();
        this._startLoop();

        // Resize observer
        this._resizeObserver = new ResizeObserver(() => this._resize());
        this._resizeObserver.observe(container);
    }

    /**
     * Unmount from current container.
     */
    unmount() {
        this._stopLoop();

        if (this._resizeObserver) {
            this._resizeObserver.disconnect();
            this._resizeObserver = null;
        }

        if (this.container && this.renderer.domElement.parentElement === this.container) {
            this.container.removeChild(this.renderer.domElement);
        }

        this.container = null;
    }

    /**
     * Dispose all resources.
     */
    dispose() {
        this.unmount();
        if (this.controls) {
            this.controls.dispose();
            this.controls = null;
        }
        if (this.renderer) {
            this.renderer.dispose();
            this.renderer = null;
        }
        this.scene = null;
        this.camera = null;
        this.renderCallbacks = [];
    }

    /**
     * Add an object to the scene.
     * @param {THREE.Object3D} obj
     */
    add(obj) {
        if (this.scene) {
            this.scene.add(obj);
        }
    }

    /**
     * Remove an object from the scene.
     * @param {THREE.Object3D} obj
     */
    remove(obj) {
        if (this.scene) {
            this.scene.remove(obj);
        }
    }

    /**
     * Register a callback called on each animation frame (for per-frame updates).
     * @param {Function} callback - (deltaTime: number) => void
     */
    addRenderer(callback) {
        this.renderCallbacks.push(callback);
    }

    /**
     * Remove a render callback.
     * @param {Function} callback
     */
    removeRenderer(callback) {
        const idx = this.renderCallbacks.indexOf(callback);
        if (idx >= 0) this.renderCallbacks.splice(idx, 1);
    }

    /**
     * Get the renderer canvas element.
     */
    getCanvas() {
        return this.renderer ? this.renderer.domElement : null;
    }

    /**
     * Enter fullscreen mode.
     */
    enterFullscreen() {
        const canvas = this.getCanvas();
        if (canvas && canvas.requestFullscreen) {
            canvas.requestFullscreen().catch(() => {});
        }
    }

    /**
     * Exit fullscreen mode.
     */
    exitFullscreen() {
        if (document.fullscreenElement && document.exitFullscreen) {
            document.exitFullscreen().catch(() => {});
        }
    }

    /**
     * Pause the animation loop.
     */
    pause() {
        this.paused = true;
    }

    /**
     * Resume the animation loop.
     */
    resume() {
        this.paused = false;
        if (!this.animationId && this.container) {
            this._startLoop();
        }
    }

    /**
     * Convert field coordinates to Three.js coordinates.
     * Field (x, y, z) -> Three.js (x, z, y), where y is up.
     * @param {{x: number, y: number, z: number}} pos
     * @returns {THREE.Vector3}
     */
    fieldToThree(pos) {
        return new THREE.Vector3(pos.x, pos.z, pos.y);
    }

    // ---- Internal ----

    _startLoop() {
        if (this.animationId) return;
        let lastTime = performance.now();

        const loop = (now) => {
            this.animationId = requestAnimationFrame(loop);

            if (this.paused) return;

            const dt = (now - lastTime) / 1000;
            lastTime = now;

            // Update controls
            if (this.controls) {
                this.controls.update();
            }

            // Call render callbacks
            for (const cb of this.renderCallbacks) {
                try {
                    cb(dt);
                } catch (e) {
                    console.error('[Scene3D] render callback error:', e);
                }
            }

            // Render
            this.renderer.render(this.scene, this.camera);
        };

        this.animationId = requestAnimationFrame(loop);
    }

    _stopLoop() {
        if (this.animationId) {
            cancelAnimationFrame(this.animationId);
            this.animationId = null;
        }
    }

    _resize() {
        if (!this.container || !this.renderer) return;
        const rect = this.container.getBoundingClientRect();
        const width = rect.width;
        const height = rect.height;

        if (width <= 0 || height <= 0) return;

        this.renderer.setSize(width, height);
        if (this.camera) {
            this.camera.aspect = width / height;
            this.camera.updateProjectionMatrix();
        }
    }
}

export { Scene3D };
