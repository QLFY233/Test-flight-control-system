/**
 * Scene3D — 3D field view (Three.js) for the right panel.
 * Renders boundary box, ground grid, home marker, and drone position.
 * Subscribes to store for real-time drone pose updates.
 */

import store from '../state.js';

class Scene3D {
    constructor() {
        this.container = null;
        this.renderer = null;
        this.scene = null;
        this.camera = null;
        this.controls = null;
        this.droneMesh = null;
        this.altLine = null;
        this.homeMesh = null;
        this.boundaryBox = null;
        this.floorMesh = null;
        this.trailLine = null;        // 绿色飞行轨迹线
        this._trailPts = [];          // 轨迹点缓冲
        this._trailLast = null;       // 上一次记录点 (去重)
        this._animationId = null;
        this._updateUnsub = null;
        this._resizeHandler = null;
        this._keys = new Set();       // WASD 移动按键
        this._lastFrame = null;       // 帧间隔计时
        this._keyDownHandler = null;
        this._keyUpHandler = null;
    }

    mount(container) {
        this.container = container;
        container.innerHTML = '';

        const el = document.createElement('div');
        el.style.width = '100%';
        el.style.height = '100%';
        el.style.position = 'relative';
        container.appendChild(el);

        if (typeof THREE === 'undefined') {
            el.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--color-text-disabled);font-size:var(--text-sm);">Three.js 加载失败（CDN 不可达）</div>';
            return;
        }

        // --- Renderer ---
        this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
        this.renderer.setPixelRatio(window.devicePixelRatio);
        this.renderer.setSize(el.clientWidth, el.clientHeight);
        this.renderer.setClearColor(0x0A0A0A, 1);
        el.appendChild(this.renderer.domElement);

        // WASD 操作提示 (左下角, 半透明)
        const hint = document.createElement('div');
        hint.style.cssText = 'position:absolute;left:8px;bottom:8px;z-index:5;font-family:var(--font-mono,monospace);font-size:10px;letter-spacing:0.08em;color:rgba(255,255,255,0.35);background:rgba(10,10,10,0.5);padding:3px 8px;pointer-events:none;user-select:none;';
        hint.textContent = '[WASD/方向键] 移动 · 左键旋转 · 滚轮缩放 · 右键平移';
        el.appendChild(hint);

        // --- Scene ---
        this.scene = new THREE.Scene();

        // --- Camera ---
        this.camera = new THREE.PerspectiveCamera(
            60, el.clientWidth / el.clientHeight, 0.1, 500
        );
        this.camera.position.set(8, 8, 6);
        this.camera.lookAt(0, 0, 0);

        // --- Controls ---
        if (typeof THREE.OrbitControls !== 'undefined') {
            this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
            this.controls.enableDamping = true;
            this.controls.dampingFactor = 0.05;
            this.controls.maxPolarAngle = Math.PI / 2 - 0.05;
        }

        // --- Lights ---
        const ambient = new THREE.AmbientLight(0x404040, 2);
        this.scene.add(ambient);
        const dirLight = new THREE.DirectionalLight(0xffffff, 1);
        dirLight.position.set(5, 10, 5);
        this.scene.add(dirLight);

        // --- Build scene ---
        this._buildSky();
        this._buildFloor();
        this._buildBoundary();
        this._buildHome();
        this._buildDrone();
        this._buildTrail();
        this._buildAxes();

        // --- Subscribe to pose updates ---
        this._updateUnsub = store.subscribe('drone', () => this._updateDrone());
        this._updateUnsubField = store.subscribe('field', () => this._updateField());

        // --- Resize ---
        this._resizeHandler = () => {
            const w = this.container.clientWidth;
            const h = this.container.clientHeight;
            if (w > 0 && h > 0) {
                this.camera.aspect = w / h;
                this.camera.updateProjectionMatrix();
                this.renderer.setSize(w, h);
            }
        };
        window.addEventListener('resize', this._resizeHandler);

        // --- WASD 键盘移动 (不抢输入框/文本框焦点) ---
        this._keyDownHandler = (e) => {
            if (store.get('ui.keyboardInputFocused')) return;  // 正在打字时不响应
            if (['KeyW', 'KeyA', 'KeyS', 'KeyD', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.code)) {
                e.preventDefault();
                this._keys.add(e.code);
            }
        };
        this._keyUpHandler = (e) => { this._keys.delete(e.code); };
        window.addEventListener('keydown', this._keyDownHandler);
        window.addEventListener('keyup', this._keyUpHandler);

        // --- Animation loop ---
        this._animate();
    }

    _buildSky() {
        // 天空: Canvas 垂直渐变背景 (深蓝黑 → 地平线暗色) + 雾
        const canvas = document.createElement('canvas');
        canvas.width = 64;
        canvas.height = 256;
        const ctx = canvas.getContext('2d');
        const grad = ctx.createLinearGradient(0, 0, 0, canvas.height);
        grad.addColorStop(0, '#0a0e1a');   // 顶部深蓝黑
        grad.addColorStop(0.6, '#0f1526');
        grad.addColorStop(1, '#1a2030');   // 地平线
        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        const tex = new THREE.CanvasTexture(canvas);
        tex.colorSpace = THREE.SRGBColorSpace;
        this.scene.background = tex;
        this.scene.fog = new THREE.Fog(0x10151f, 80, 300);  // 雾远置, 避免遮挡近处地板
    }

    // 场地边界统一解析: 兼容 {x:[min,max],y:[min,max],z:[min,max]} 与旧 {xMin,xMax,...} 两种格式
    _boundary() {
        const field = store.get('field') || {};
        const b = field.boundary || {};
        if (Array.isArray(b.x)) {
            return { xMin: b.x[0], xMax: b.x[1], yMin: b.y[0], yMax: b.y[1], zMin: b.z[0], zMax: b.z[1] };
        }
        return {
            xMin: b.xMin ?? -50, xMax: b.xMax ?? 50,
            yMin: b.yMin ?? -50, yMax: b.yMax ?? 50,
            zMin: b.zMin ?? 0, zMax: b.zMax ?? 30,
        };
    }

    // HOME 统一解析: 兼容 {position:[x,y,z],yaw} 与旧 {x,y,z} 两种格式
    _home() {
        const field = store.get('field') || {};
        const h = field.home || {};
        if (Array.isArray(h.position)) {
            return { x: h.position[0], y: h.position[1], z: h.position[2], yaw: h.yaw || 0 };
        }
        return { x: h.x ?? 0, y: h.y ?? 0, z: h.z ?? 0, yaw: h.yaw || 0 };
    }

    _buildFloor() {
        // 地板: 一大块石头色平板 (纯色, 简洁), 铺在 zMin 处
        const b = this._boundary();
        const size = Math.max(b.xMax - b.xMin, b.yMax - b.yMin, 20) * 2.5;

        const mat = new THREE.MeshStandardMaterial({
            color: 0x8a8a88,        // 石头灰
            metalness: 0.05,
            roughness: 0.9,
            transparent: false,
        });
        this.floorMesh = new THREE.Mesh(new THREE.PlaneGeometry(size, size), mat);
        this.floorMesh.rotation.x = -Math.PI / 2;
        this.floorMesh.position.set(
            (b.xMin + b.xMax) / 2, b.zMin, (b.yMin + b.yMax) / 2
        );
        this.scene.add(this.floorMesh);
    }

    _buildBoundary() {
        const b = this._boundary();

        // Clear old
        if (this.boundaryBox) { this.scene.remove(this.boundaryBox); this.boundaryBox = null; }

        // ENU → Three.js: x→x(东), z→y(高), y→z(北)
        const geo = new THREE.BoxGeometry(
            b.xMax - b.xMin, b.zMax - b.zMin, b.yMax - b.yMin
        );
        const edges = new THREE.EdgesGeometry(geo);
        const mat = new THREE.LineBasicMaterial({ color: 0x00BCD4, transparent: true, opacity: 0.4 });
        this.boundaryBox = new THREE.LineSegments(edges, mat);
        this.boundaryBox.position.set(
            (b.xMin + b.xMax) / 2,
            (b.zMin + b.zMax) / 2,
            (b.yMin + b.yMax) / 2
        );
        this.scene.add(this.boundaryBox);
    }

    _buildHome() {
        const home = this._home();

        // Diamond shape (home marker) — ENU: x→x, z→y(高), y→z
        const geo = new THREE.ConeGeometry(0.3, 0.6, 4);
        const mat = new THREE.MeshBasicMaterial({ color: 0x4CAF50 });
        this.homeMesh = new THREE.Mesh(geo, mat);
        this.homeMesh.rotation.x = Math.PI;
        this.homeMesh.position.set(home.x, home.z + 0.3, home.y);
        this.scene.add(this.homeMesh);

        // Label (simple sprite)
        const canvas = document.createElement('canvas');
        canvas.width = 128; canvas.height = 32;
        const ctx = canvas.getContext('2d');
        ctx.font = 'bold 16px monospace';
        ctx.fillStyle = '#4CAF50';
        ctx.textAlign = 'center';
        ctx.fillText('HOME', 64, 22);
        const tex = new THREE.CanvasTexture(canvas);
        const spriteMat = new THREE.SpriteMaterial({ map: tex });
        const sprite = new THREE.Sprite(spriteMat);
        sprite.scale.set(1.5, 0.375, 1);
        sprite.position.set(home.x, home.z + 1.0, home.y);
        this.scene.add(sprite);
    }

    _buildDrone() {
        // Simple drone: box body + 4 rotors (Three.js 水平面为 XZ，竖直方向为 Y)
        const group = new THREE.Group();

        // Body
        const bodyGeo = new THREE.BoxGeometry(0.3, 0.1, 0.3);
        const bodyMat = new THREE.MeshStandardMaterial({ color: 0x00BCD4 });
        const body = new THREE.Mesh(bodyGeo, bodyMat);
        group.add(body);

        // Rotors (4 small cylinders, 在机体上方 y=0.05)
        const rotorGeo = new THREE.CylinderGeometry(0.15, 0.15, 0.02, 8);
        const rotorMat = new THREE.MeshBasicMaterial({ color: 0xFF5722 });
        const offsets = [
            [-0.2, 0.05, -0.2], [0.2, 0.05, -0.2],
            [-0.2, 0.05, 0.2], [0.2, 0.05, 0.2],
        ];
        offsets.forEach(off => {
            const rotor = new THREE.Mesh(rotorGeo, rotorMat);
            rotor.position.set(off[0], off[1], off[2]);
            group.add(rotor);
        });

        this.droneMesh = group;
        this.scene.add(this.droneMesh);

        // 高度参考线（从无人机垂直落到地面，便于读高度）
        const lineGeo = new THREE.BufferGeometry();
        const lineMat = new THREE.LineBasicMaterial({ color: 0xFF5722, transparent: true, opacity: 0.5 });
        this.altLine = new THREE.Line(lineGeo, lineMat);
        this.scene.add(this.altLine);

        this._updateDrone();
    }

    _buildTrail() {
        // 绿色飞行轨迹线 (动态缓冲, 无人机移动时追加点)
        const geo = new THREE.BufferGeometry();
        geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(0), 3));
        const mat = new THREE.LineBasicMaterial({ color: 0x00E676, linewidth: 2 });
        this.trailLine = new THREE.Line(geo, mat);
        this.trailLine.frustumCulled = false;
        this.scene.add(this.trailLine);
    }

    _buildAxes() {
        const axes = new THREE.AxesHelper(3);
        this.scene.add(axes);
    }

    _updateDrone() {
        if (!this.droneMesh) return;
        const drone = store.get('drone');
        if (drone && drone.position) {
            const x = drone.position.x || 0;
            const z = drone.position.z || 0;
            const y = drone.position.y || 0;
            // 落地时 z 可能低于地板(zMin) → 被不透明地板遮挡消失。显示高度钳制到地板平面,
            // 让落地无人机显示为停在平面上 (2026-08-04)
            const groundY = this._boundary().zMin || 0;
            const displayZ = Math.max(z, groundY);
            // ENU → Three.js: x→x(东), z→y(高), y→z(北)
            this.droneMesh.position.set(x, displayZ, y);

            // yaw 从四元数 [w,x,y,z] 计算 (drone.attitude.quat)
            const q = drone.attitude?.quat;
            let yaw = drone.attitude?.yaw || 0;
            if (Array.isArray(q) && q.length === 4) {
                const [qw, qx, qy, qz] = q;
                yaw = Math.atan2(2 * (qw * qz + qx * qy), 1 - 2 * (qy * qy + qz * qz));
            }
            this.droneMesh.rotation.y = yaw;

            // 高度参考线
            if (this.altLine) {
                this.altLine.geometry.setFromPoints([
                    new THREE.Vector3(x, groundY, y),
                    new THREE.Vector3(x, displayZ, y),
                ]);
            }

            // 飞行轨迹: 记录移动点 (去重, 缓冲上限)
            this._appendTrailPoint(x, displayZ, y);
        }
    }

    _appendTrailPoint(x, y, z) {
        if (!this.trailLine) return;
        const MIN_STEP = 0.02;        // 移动超过此距离才记录 (悬停不堆积点)
        const MAX_POINTS = 3000;      // 轨迹点缓冲上限

        if (this._trailLast && Math.abs(x - this._trailLast[0]) < MIN_STEP &&
            Math.abs(y - this._trailLast[1]) < MIN_STEP && Math.abs(z - this._trailLast[2]) < MIN_STEP) {
            return;
        }
        this._trailLast = [x, y, z];
        this._trailPts.push(x, y, z);
        if (this._trailPts.length > MAX_POINTS * 3) {
            this._trailPts.splice(0, this._trailPts.length - MAX_POINTS * 3);
        }
        this.trailLine.geometry.setAttribute('position',
            new THREE.BufferAttribute(new Float32Array(this._trailPts), 3));
        this.trailLine.geometry.attributes.position.needsUpdate = true;
        this.trailLine.geometry.computeBoundingSphere();
    }

    _updateField() {
        if (this.floorMesh) { this.scene.remove(this.floorMesh); this.floorMesh = null; }
        this._buildFloor();
        this._buildBoundary();
        if (this.homeMesh) { this.scene.remove(this.homeMesh); this.homeMesh = null; }
        this._buildHome();
    }

    _animate() {
        this._animationId = requestAnimationFrame(() => this._animate());

        // WASD/方向键 平移相机 (沿水平面, 相对镜头朝向)
        if (this.camera && this._keys.size > 0) {
            const now = performance.now();
            const dt = this._lastFrame === null ? 0 : Math.min((now - this._lastFrame) / 1000, 0.05);
            this._lastFrame = now;
            this._moveCamera(dt);
        } else {
            this._lastFrame = null;
        }

        if (this.controls) this.controls.update();
        if (this.renderer && this.scene && this.camera) {
            this.renderer.render(this.scene, this.camera);
        }
    }

    _moveCamera(dt) {
        const speed = 6.0;   // m/s
        const forward = new THREE.Vector3();
        this.camera.getWorldDirection(forward);
        forward.y = 0;                 // 只沿水平面
        if (forward.lengthSq() > 0) forward.normalize();

        const right = new THREE.Vector3().crossVectors(forward, new THREE.Vector3(0, 1, 0));
        if (right.lengthSq() > 0) right.normalize();

        const move = new THREE.Vector3();
        const k = this._keys;
        if (k.has('KeyW') || k.has('ArrowUp')) move.add(forward);
        if (k.has('KeyS') || k.has('ArrowDown')) move.sub(forward);
        if (k.has('KeyA') || k.has('ArrowLeft')) move.sub(right);
        if (k.has('KeyD') || k.has('ArrowRight')) move.add(right);
        if (move.lengthSq() === 0) return;

        const delta = move.normalize().multiplyScalar(speed * dt);
        this.camera.position.add(delta);
        // 同步移动 OrbitControls target, 保持视角朝向不变 (避免 controls.update 回跳)
        if (this.controls) this.controls.target.add(delta);
    }

    unmount() {
        if (this._animationId) { cancelAnimationFrame(this._animationId); this._animationId = null; }
        if (this._updateUnsub) { this._updateUnsub(); this._updateUnsub = null; }
        if (this._updateUnsubField) { this._updateUnsubField(); this._updateUnsubField = null; }
        if (this._resizeHandler) { window.removeEventListener('resize', this._resizeHandler); this._resizeHandler = null; }
        if (this._keyDownHandler) { window.removeEventListener('keydown', this._keyDownHandler); this._keyDownHandler = null; }
        if (this._keyUpHandler) { window.removeEventListener('keyup', this._keyUpHandler); this._keyUpHandler = null; }
        if (this.controls) { this.controls.dispose(); this.controls = null; }
        if (this.renderer) { this.renderer.dispose(); this.renderer = null; }
        this.scene = null;
        this.camera = null;
        this.container = null;
    }
}

export { Scene3D };
