/**
 * DroneModel — Quadcopter 3D model from basic geometries.
 * Self-updates position/orientation via linear interpolation.
 * Rotor spin speed proportional to velocity magnitude.
 */

class DroneModel {
    constructor(scene3D) {
        this.scene3D = scene3D;
        this.group = new THREE.Group();
        this.targetPosition = new THREE.Vector3(0, 0, 0);
        this.currentPosition = new THREE.Vector3(0, 0, 0);
        this.targetQuaternion = new THREE.Quaternion();
        this.currentQuaternion = new THREE.Quaternion();
        this.rotors = [];
        this.currentVelocity = 0;
        this.visible = true;

        this._build();

        scene3D.add(this.group);
        scene3D.addRenderer((dt) => this._update(dt));
    }

    _build() {
        const bodyColor = 0x333333;
        const armColor = 0x444444;
        const rotorColor = 0x666666;

        // Body
        const bodyGeo = new THREE.BoxGeometry(1.2, 0.15, 0.8);
        const bodyMat = new THREE.MeshStandardMaterial({
            color: bodyColor,
            roughness: 0.4,
            metalness: 0.6,
        });
        const body = new THREE.Mesh(bodyGeo, bodyMat);
        body.castShadow = true;
        body.position.y = 0.15;
        this.group.add(body);

        // Arms (4 cylinders extending from body)
        const armLength = 0.7;
        const armGeo = new THREE.CylinderGeometry(0.04, 0.04, armLength, 8);
        const armMat = new THREE.MeshStandardMaterial({
            color: armColor,
            roughness: 0.5,
            metalness: 0.4,
        });

        const armPositions = [
            { x: 0.5, z: 0, rotZ: 0 },          // Front
            { x: -0.5, z: 0, rotZ: 0 },         // Back
            { x: 0, z: 0.35, rotZ: Math.PI / 2 }, // Right
            { x: 0, z: -0.35, rotZ: Math.PI / 2 }, // Left
        ];

        const rotorGeo = new THREE.TorusGeometry(0.2, 0.03, 8, 16);
        const rotorMat = new THREE.MeshStandardMaterial({
            color: rotorColor,
            roughness: 0.3,
            metalness: 0.7,
        });

        for (const ap of armPositions) {
            // Arm
            const arm = new THREE.Mesh(armGeo, armMat);
            arm.position.set(ap.x, 0.15, ap.z);
            arm.rotation.z = ap.rotZ;
            arm.castShadow = true;
            this.group.add(arm);

            // Rotor (ring) on top
            const rotor = new THREE.Mesh(rotorGeo, rotorMat);
            rotor.position.set(ap.x, 0.3, ap.z);
            rotor.rotation.x = Math.PI / 2;
            this.rotors.push(rotor);
            this.group.add(rotor);

            // Motor hub
            const hubGeo = new THREE.CylinderGeometry(0.07, 0.07, 0.06, 8);
            const hub = new THREE.Mesh(hubGeo, armMat);
            hub.position.set(ap.x, 0.28, ap.z);
            this.group.add(hub);
        }
    }

    /**
     * Set target position for smooth interpolation.
     * Position in field coordinates (x, y, z), gets converted to Three.js (x, z, y).
     * @param {{x: number, y: number, z: number}} pos
     */
    setTargetPosition(pos) {
        this.targetPosition.set(pos.x, pos.z, pos.y);
        // Calculate velocity from position change
        const dx = pos.x - this.currentPosition.x;
        const dy = pos.z - this.currentPosition.z;
        const dz = pos.y - this.currentPosition.y;
        this.currentVelocity = Math.sqrt(dx * dx + dy * dy + dz * dz);
    }

    /**
     * Set target quaternion (orientation).
     * @param {THREE.Quaternion|{x: number, y: number, z: number, w: number}} quat
     */
    setTargetQuaternion(quat) {
        if (quat instanceof THREE.Quaternion) {
            this.targetQuaternion.copy(quat);
        } else if (quat && quat.x !== undefined) {
            this.targetQuaternion.set(quat.x, quat.y, quat.z, quat.w);
        }
    }

    /**
     * Set visibility.
     */
    setVisible(v) {
        this.visible = v;
        this.group.visible = v;
    }

    /**
     * Remove from scene.
     */
    dispose() {
        this.scene3D.remove(this.group);
        this._disposeGroup(this.group);
        this.rotors = [];
    }

    // ---- Internal ----

    _update(dt) {
        if (!this.visible) return;

        // Smoothly interpolate position
        const lerpFactor = Math.min(1, dt * 15);
        this.currentPosition.lerp(this.targetPosition, lerpFactor);
        this.group.position.copy(this.currentPosition);

        // Smoothly interpolate rotation
        this.currentQuaternion.slerp(this.targetQuaternion, lerpFactor);
        this.group.quaternion.copy(this.currentQuaternion);

        // Rotor spin (proportional to velocity, base speed)
        const baseSpeed = 30;
        const rotorSpeed = baseSpeed + this.currentVelocity * 10;
        for (const rotor of this.rotors) {
            rotor.rotation.z += rotorSpeed * dt;
        }
    }

    _disposeGroup(group) {
        while (group.children.length > 0) {
            const child = group.children[0];
            if (child.geometry) child.geometry.dispose();
            if (child.material) {
                if (Array.isArray(child.material)) {
                    child.material.forEach(m => m.dispose());
                } else {
                    child.material.dispose();
                }
            }
            group.remove(child);
        }
    }
}

export { DroneModel };
