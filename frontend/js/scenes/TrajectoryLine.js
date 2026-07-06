/**
 * TrajectoryLine — Renders flown (green) and planned (cyan dashed) trajectory lines.
 * Auto-merges old points when count exceeds 10000.
 * Points in field coordinates (x, y, z), converted to Three.js (x, z, y).
 */

class TrajectoryLine {
    constructor(scene3D) {
        this.scene3D = scene3D;
        this.flownGroup = new THREE.Group();
        this.plannedGroup = new THREE.Group();
        this.flownPoints = [];
        this.plannedPoints = [];
        this.maxPoints = 10000;
        this.mergeThreshold = 5000;
        this.visible = true;

        scene3D.add(this.flownGroup);
        scene3D.add(this.plannedGroup);
    }

    /**
     * Append flown points.
     * @param {Array<{x: number, y: number, z: number, t?: number}>} points
     */
    updateFlown(points) {
        if (!points || points.length === 0) return;
        this.flownPoints.push(...points);

        // Auto-merge if too many points
        if (this.flownPoints.length > this.maxPoints) {
            this._mergePoints(this.flownPoints);
        }

        this._redrawFlown();
    }

    /**
     * Set planned trajectory (replaces existing).
     * @param {Array<{x: number, y: number, z: number}>} points
     */
    setPlanned(points) {
        this.plannedPoints = points || [];
        this._redrawPlanned();
    }

    /**
     * Set visibility.
     */
    setVisible(v) {
        this.visible = v;
        this.flownGroup.visible = v;
        this.plannedGroup.visible = v;
    }

    /**
     * Clear all trajectory lines.
     */
    clear() {
        this.flownPoints = [];
        this.plannedPoints = [];
        this._clearGroup(this.flownGroup);
        this._clearGroup(this.plannedGroup);
    }

    /**
     * Remove from scene.
     */
    dispose() {
        this.clear();
        this.scene3D.remove(this.flownGroup);
        this.scene3D.remove(this.plannedGroup);
    }

    // ---- Internal ----

    _redrawFlown() {
        this._clearGroup(this.flownGroup);

        if (this.flownPoints.length < 2) return;

        const positions = this.flownPoints.map(p =>
            new THREE.Vector3(p.x, p.z, p.y)
        );

        const geometry = new THREE.BufferGeometry().setFromPoints(positions);
        const material = new THREE.LineBasicMaterial({
            color: 0x4caf50,
            linewidth: 1, // Note: linewidth > 1 not supported on Windows WebGL
        });
        const line = new THREE.Line(geometry, material);
        this.flownGroup.add(line);
    }

    _redrawPlanned() {
        this._clearGroup(this.plannedGroup);

        if (this.plannedPoints.length < 2) return;

        const positions = this.plannedPoints.map(p =>
            new THREE.Vector3(p.x, p.z, p.y)
        );

        const geometry = new THREE.BufferGeometry().setFromPoints(positions);
        const material = new THREE.LineDashedMaterial({
            color: 0x00bcd4,
            dashSize: 1,
            gapSize: 0.5,
            linewidth: 1,
        });
        const line = new THREE.Line(geometry, material);
        line.computeLineDistances();
        this.plannedGroup.add(line);
    }

    _mergePoints(points) {
        // Merge every 2 points into 1 (average position) to reduce count
        const merged = [];
        for (let i = 0; i < points.length; i += 2) {
            if (i + 1 < points.length) {
                merged.push({
                    x: (points[i].x + points[i + 1].x) / 2,
                    y: (points[i].y + points[i + 1].y) / 2,
                    z: (points[i].z + points[i + 1].z) / 2,
                    t: points[i].t,
                });
            } else {
                merged.push(points[i]);
            }
        }
        this.flownPoints = merged;
    }

    _clearGroup(group) {
        while (group.children.length > 0) {
            const child = group.children[0];
            if (child.geometry) child.geometry.dispose();
            if (child.material) child.material.dispose();
            group.remove(child);
        }
    }
}

export { TrajectoryLine };
