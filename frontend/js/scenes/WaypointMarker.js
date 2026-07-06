/**
 * WaypointMarker — Renders waypoints as numbered spheres with sprite labels,
 * and the current target as a glowing pulsing sphere.
 * Coordinates: field (x, y, z) -> Three.js (x, z, y).
 */

class WaypointMarker {
    constructor(scene3D) {
        this.scene3D = scene3D;
        this.waypointsGroup = new THREE.Group();
        this.targetGroup = new THREE.Group();
        this.targetMesh = null;
        this.targetGlowTime = 0;
        this.visible = true;

        scene3D.add(this.waypointsGroup);
        scene3D.add(this.targetGroup);

        // Register render callback for target glow animation
        scene3D.addRenderer((dt) => this._updateTargetGlow(dt));
    }

    /**
     * Set the current target waypoint (glowing pulsing sphere).
     * @param {{x: number, y: number, z: number}} pos
     */
    setTarget(pos) {
        this._clearGroup(this.targetGroup);
        if (!pos) return;

        // Main sphere
        const geo = new THREE.SphereGeometry(0.25, 16, 16);
        const mat = new THREE.MeshStandardMaterial({
            color: 0x00bcd4,
            roughness: 0.2,
            metalness: 0.3,
            emissive: 0x00bcd4,
            emissiveIntensity: 0.8,
        });
        this.targetMesh = new THREE.Mesh(geo, mat);
        this.targetMesh.position.set(pos.x, pos.z, pos.y);

        // Outer glow ring
        const ringGeo = new THREE.TorusGeometry(0.35, 0.04, 8, 24);
        const ringMat = new THREE.MeshStandardMaterial({
            color: 0x00bcd4,
            roughness: 0.1,
            emissive: 0x00bcd4,
            emissiveIntensity: 1.0,
            transparent: true,
            opacity: 0.7,
        });
        const ring = new THREE.Mesh(ringGeo, ringMat);
        this.targetMesh.add(ring);

        this.targetGroup.add(this.targetMesh);
    }

    /**
     * Set waypoints.
     * @param {Array<{x: number, y: number, z: number, label?: string}>} points
     */
    setWaypoints(points) {
        this._clearGroup(this.waypointsGroup);
        if (!points || points.length === 0) return;

        for (let i = 0; i < points.length; i++) {
            const wp = points[i];
            const pos = new THREE.Vector3(wp.x, wp.z, wp.y);

            // Small sphere
            const geo = new THREE.SphereGeometry(0.15, 8, 8);
            const mat = new THREE.MeshStandardMaterial({
                color: 0x4dd0e1,
                roughness: 0.4,
                metalness: 0.3,
                emissive: 0x0097a7,
                emissiveIntensity: 0.4,
            });
            const sphere = new THREE.Mesh(geo, mat);
            sphere.position.copy(pos);
            this.waypointsGroup.add(sphere);

            // Number label via sprite
            const label = wp.label || String(i + 1);
            const sprite = this._createLabel(label, pos);
            this.waypointsGroup.add(sprite);
        }
    }

    /**
     * Set visibility.
     */
    setVisible(v) {
        this.visible = v;
        this.waypointsGroup.visible = v;
        this.targetGroup.visible = v;
    }

    /**
     * Clear all markers.
     */
    clear() {
        this._clearGroup(this.waypointsGroup);
        this._clearGroup(this.targetGroup);
        this.targetMesh = null;
    }

    /**
     * Remove from scene.
     */
    dispose() {
        this.clear();
        this.scene3D.remove(this.waypointsGroup);
        this.scene3D.remove(this.targetGroup);
    }

    // ---- Internal ----

    _createLabel(text, position) {
        // Create canvas texture for sprite label
        const canvas = document.createElement('canvas');
        canvas.width = 128;
        canvas.height = 64;
        const ctx = canvas.getContext('2d');
        ctx.fillStyle = '#00BCD4';
        ctx.font = 'bold 32px Arial';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(text, 64, 32);

        const texture = new THREE.CanvasTexture(canvas);
        texture.minFilter = THREE.LinearFilter;
        const material = new THREE.SpriteMaterial({
            map: texture,
            transparent: true,
            depthTest: false,
        });
        const sprite = new THREE.Sprite(material);
        sprite.position.copy(position);
        sprite.position.y += 0.4; // Offset above the sphere
        sprite.scale.set(1.5, 0.75, 1);
        return sprite;
    }

    _updateTargetGlow(dt) {
        if (!this.targetMesh || !this.visible) return;

        this.targetGlowTime += dt;
        const scale = 1 + Math.sin(this.targetGlowTime * 4) * 0.2;
        this.targetMesh.scale.setScalar(scale);

        // Pulsing emissive intensity
        if (this.targetMesh.material && this.targetMesh.material.emissiveIntensity !== undefined) {
            this.targetMesh.material.emissiveIntensity = 0.6 + Math.sin(this.targetGlowTime * 4) * 0.4;
        }
    }

    _clearGroup(group) {
        while (group.children.length > 0) {
            const child = group.children[0];
            if (child.geometry) child.geometry.dispose();
            if (child.material) {
                if (child.material.map) child.material.map.dispose();
                child.material.dispose();
            }
            group.remove(child);
        }
    }
}

export { WaypointMarker };
