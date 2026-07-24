/**
 * LidarPointCloud — Placeholder for LiDAR point cloud visualization.
 *
 * Phase 1: Not implemented. Shows a "no data" indicator.
 * Phase 2/4: Will render real-time LiDAR point cloud from /lidar topic.
 */

class LidarPointCloud {
    constructor(scene3D) {
        this.scene3D = scene3D;
        this.group = new THREE.Group();
        this.visible = false;
        scene3D.add(this.group);
    }

    /**
     * Update point cloud from LiDAR data.
     * @param {Array<{x:number,y:number,z:number}>} points
     */
    update(points) {
        // Phase 1: not implemented — LiDAR data not available yet.
        // Phase 2/4: Clear old points, create new BufferGeometry with Positions,
        //            use PointsMaterial with size attenuation.
        if (!points || points.length === 0) {
            this.clear();
            return;
        }
        // Stub: log received data length for debugging
        console.log(`[LidarPointCloud] received ${points.length} points (Phase 1: not rendering)`);
    }

    /**
     * Show the point cloud.
     */
    show() {
        this.visible = true;
        this.group.visible = true;
    }

    /**
     * Hide the point cloud.
     */
    hide() {
        this.visible = false;
        this.group.visible = false;
    }

    /**
     * Clear all points.
     */
    clear() {
        while (this.group.children.length > 0) {
            const child = this.group.children[0];
            if (child.geometry) child.geometry.dispose();
            if (child.material) child.material.dispose();
            this.group.remove(child);
        }
    }

    /**
     * Dispose all resources.
     */
    dispose() {
        this.clear();
        if (this.scene3D) {
            this.scene3D.remove(this.group);
        }
    }
}

export { LidarPointCloud };
