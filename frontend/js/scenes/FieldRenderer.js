/**
 * FieldRenderer — Renders field boundary, ground grid, obstacles, and home position.
 * Reads from store.field.
 */

import store from '../state.js';

class FieldRenderer {
    constructor(scene3D) {
        this.scene3D = scene3D;
        this.group = new THREE.Group();
        this.gridHelper = null;
        this.boundaryLines = null;
        this.obstaclesGroup = new THREE.Group();
        this.homeMarker = null;

        scene3D.add(this.group);
        this.group.add(this.obstaclesGroup);
        this._createGrid();
    }

    /**
     * Update all field elements from field data.
     * @param {object} field - { boundary, obstacles, home }
     */
    updateFromField(field) {
        if (!field) return;

        this._updateBoundary(field.boundary);
        this._updateObstacles(field.obstacles || []);
        this._updateHome(field.home);
    }

    _createGrid() {
        // Large ground grid
        this.gridHelper = new THREE.GridHelper(100, 50, 0x1a1a1a, 0x111111);
        this.gridHelper.position.y = 0;
        this.group.add(this.gridHelper);

        // Add a slightly darker ground plane for depth
        const groundGeo = new THREE.PlaneGeometry(100, 100);
        const groundMat = new THREE.MeshStandardMaterial({
            color: 0x111111,
            roughness: 0.9,
            metalness: 0.0,
            side: THREE.DoubleSide,
        });
        const ground = new THREE.Mesh(groundGeo, groundMat);
        ground.rotation.x = -Math.PI / 2;
        ground.position.y = -0.01;
        ground.receiveShadow = true;
        this.group.add(ground);
    }

    _updateBoundary(boundary) {
        if (this.boundaryLines) {
            this.group.remove(this.boundaryLines);
            this._disposeObject(this.boundaryLines);
            this.boundaryLines = null;
        }

        if (!boundary) return;

        const { xMin, xMax, yMin, yMax, zMin = 0, zMax = 30 } = boundary;

        // Create wireframe box
        const w = xMax - xMin;
        const d = yMax - yMin; // y in field is depth
        const h = zMax - zMin;

        // Center in field coords; convert to Three.js (x, z, y)
        const boxGeo = new THREE.BoxGeometry(w, h, d);
        const edges = new THREE.EdgesGeometry(boxGeo);
        const lineMat = new THREE.LineBasicMaterial({
            color: 0x00bcd4,
            transparent: true,
            opacity: 0.3,
        });
        this.boundaryLines = new THREE.LineSegments(edges, lineMat);

        // Position in Three.js: field (cx, cy, cz) -> Three.js (cx, cz, cy)
        const cx = (xMin + xMax) / 2;
        const cy = (yMin + yMax) / 2;
        const cz = (zMin + zMax) / 2;
        this.boundaryLines.position.set(cx, h / 2 + zMin, cy);

        this.group.add(this.boundaryLines);
    }

    _updateObstacles(obstacles) {
        // Clear old
        while (this.obstaclesGroup.children.length > 0) {
            const child = this.obstaclesGroup.children[0];
            this._disposeObject(child);
            this.obstaclesGroup.remove(child);
        }

        if (!obstacles || obstacles.length === 0) return;

        const mat = new THREE.MeshStandardMaterial({
            color: 0xffc107,
            roughness: 0.6,
            metalness: 0.1,
            transparent: true,
            opacity: 0.5,
        });

        for (const obs of obstacles) {
            const pos = obs.position || { x: 0, y: 0, z: 0 };
            const size = obs.size || {};

            let geometry;
            switch (obs.type) {
                case 'cylinder':
                    geometry = new THREE.CylinderGeometry(
                        size.radius || 1,
                        size.radius || 1,
                        size.height || 5,
                        16
                    );
                    break;
                case 'sphere':
                    geometry = new THREE.SphereGeometry(size.radius || 1, 16, 16);
                    break;
                case 'box':
                default:
                    geometry = new THREE.BoxGeometry(
                        size.width || 2,
                        size.height || 5,
                        size.depth || 2
                    );
                    break;
            }

            const mesh = new THREE.Mesh(geometry, mat.clone());
            mesh.position.set(pos.x, (size.height || 5) / 2 + (pos.z || 0), pos.y);
            mesh.castShadow = true;
            mesh.receiveShadow = true;

            // Wireframe overlay for visibility
            const edges = new THREE.EdgesGeometry(geometry);
            const edgeLine = new THREE.LineSegments(
                edges,
                new THREE.LineBasicMaterial({ color: 0xff8f00, transparent: true, opacity: 0.6 })
            );
            mesh.add(edgeLine);

            this.obstaclesGroup.add(mesh);
        }
    }

    _updateHome(home) {
        if (this.homeMarker) {
            this.group.remove(this.homeMarker);
            this._disposeObject(this.homeMarker);
            this.homeMarker = null;
        }

        if (!home) return;

        const pos = home;
        // Disc marker
        const geo = new THREE.CylinderGeometry(0.5, 0.5, 0.1, 32);
        const mat = new THREE.MeshStandardMaterial({
            color: 0x4caf50,
            roughness: 0.3,
            metalness: 0.5,
            transparent: true,
            opacity: 0.7,
            emissive: 0x2e7d32,
            emissiveIntensity: 0.3,
        });
        this.homeMarker = new THREE.Mesh(geo, mat);
        this.homeMarker.position.set(pos.x, 0.05, pos.y);

        // Ring
        const ringGeo = new THREE.TorusGeometry(0.6, 0.05, 8, 24);
        const ringMat = new THREE.MeshStandardMaterial({
            color: 0x4caf50,
            roughness: 0.3,
            emissive: 0x2e7d32,
            emissiveIntensity: 0.5,
        });
        const ring = new THREE.Mesh(ringGeo, ringMat);
        ring.rotation.x = -Math.PI / 2;
        ring.position.y = 0.06;
        this.homeMarker.add(ring);

        this.group.add(this.homeMarker);
    }

    /**
     * Remove all field elements.
     */
    clear() {
        if (this.boundaryLines) {
            this.group.remove(this.boundaryLines);
            this._disposeObject(this.boundaryLines);
            this.boundaryLines = null;
        }
        while (this.obstaclesGroup.children.length > 0) {
            const child = this.obstaclesGroup.children[0];
            this._disposeObject(child);
            this.obstaclesGroup.remove(child);
        }
        if (this.homeMarker) {
            this.group.remove(this.homeMarker);
            this._disposeObject(this.homeMarker);
            this.homeMarker = null;
        }
    }

    _disposeObject(obj) {
        if (obj.geometry) obj.geometry.dispose();
        if (obj.material) {
            if (Array.isArray(obj.material)) {
                obj.material.forEach(m => m.dispose());
            } else {
                obj.material.dispose();
            }
        }
        // Recurse children
        while (obj.children && obj.children.length > 0) {
            this._disposeObject(obj.children[0]);
            obj.remove(obj.children[0]);
        }
    }
}

export { FieldRenderer };
