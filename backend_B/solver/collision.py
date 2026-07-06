"""
Collision detection for sampled trajectory points.

Supports four obstacle types:
  - box: AABB distance check
  - cylinder: XY distance to axis check
  - sphere: center distance check
  - plane: normal side check

All checks incorporate `keep_clear_distance` margin.
"""

import math
from typing import Optional


def check_sample(
    sample_xyz: list,
    obstacle: dict,
    keep_clear_distance: float,
) -> bool:
    """
    Check a single sample point against a single obstacle.

    Args:
        sample_xyz: [x, y, z] position to check.
        obstacle: Obstacle dict with 'type' and type-specific fields.
        keep_clear_distance: Safety margin in meters.

    Returns:
        True if collision / violation detected, False if clear.
    """
    x, y, z = sample_xyz[0], sample_xyz[1], sample_xyz[2]
    obs_type = obstacle.get("type", "box")
    margin = keep_clear_distance

    if obs_type == "box":
        return _check_box(x, y, z, obstacle, margin)
    elif obs_type == "cylinder":
        return _check_cylinder(x, y, z, obstacle, margin)
    elif obs_type == "sphere":
        return _check_sphere(x, y, z, obstacle, margin)
    elif obs_type == "plane":
        return _check_plane(x, y, z, obstacle, margin)
    else:
        # Unknown type: treat as sphere for safety
        return _check_sphere(x, y, z, obstacle, margin)


def _check_box(x: float, y: float, z: float, obs: dict, margin: float) -> bool:
    """
    Check against an axis-aligned box obstacle.

    A collision is detected if the point lies within the expanded box
    (original box extended by margin on all sides).
    """
    center = obs.get("center", [0.0, 0.0, 0.0])
    size = obs.get("size", [1.0, 1.0, 1.0])

    cx, cy, cz = center[0], center[1], center[2]
    sx, sy, sz = size[0], size[1], size[2]

    half_sx = sx / 2.0 + margin
    half_sy = sy / 2.0 + margin
    half_sz = sz / 2.0 + margin

    if (cx - half_sx <= x <= cx + half_sx and
        cy - half_sy <= y <= cy + half_sy and
        cz - half_sz <= z <= cz + half_sz):
        return True

    return False


def _check_cylinder(x: float, y: float, z: float, obs: dict, margin: float) -> bool:
    """
    Check against a vertical cylinder obstacle.

    The cylinder is defined by center (x,y,z of base), radius, and height.
    It extends from center_z to center_z + height.
    """
    center = obs.get("center", [0.0, 0.0, 0.0])
    radius = obs.get("radius", 0.3)
    height = obs.get("height", 3.0)

    cx, cy, cz = center[0], center[1], center[2]

    # Z-axis check (cylinder extends upward from cz)
    if (cz - margin) <= z <= (cz + height + margin):
        # XY distance to cylinder axis
        dx = x - cx
        dy = y - cy
        dist_xy = math.sqrt(dx * dx + dy * dy)

        if dist_xy <= (radius + margin):
            return True

    return False


def _check_sphere(x: float, y: float, z: float, obs: dict, margin: float) -> bool:
    """
    Check against a spherical obstacle.

    Collision if 3D distance from center <= radius + margin.
    """
    center = obs.get("center", [0.0, 0.0, 0.0])
    radius = obs.get("radius", 0.3)

    cx, cy, cz = center[0], center[1], center[2]

    dx = x - cx
    dy = y - cy
    dz = z - cz
    dist = math.sqrt(dx * dx + dy * dy + dz * dz)

    return dist <= (radius + margin)


def _check_plane(x: float, y: float, z: float, obs: dict, margin: float) -> bool:
    """
    Check against a plane obstacle.

    The plane is defined by a point and a normal vector.
    Violation is detected if the sample is on the "wrong" side of the plane
    (i.e., dot(point - sample, normal) < margin), meaning the drone is too
    close to or has crossed the forbidden plane.

    For a boundary plane like "right boundary (no crossing)":
    - Normal points into the allowed region.
    - Sample is safe if it is at least margin distance from the plane
      in the normal direction.
    """
    point = obs.get("point", [0.0, 0.0, 0.0])
    normal = obs.get("normal", [1.0, 0.0, 0.0])

    px, py, pz = point[0], point[1], point[2]
    nx, ny, nz = normal[0], normal[1], normal[2]

    # Compute signed distance: dot(sample - point, normal)
    signed_dist = (x - px) * nx + (y - py) * ny + (z - pz) * nz

    # If signed distance < margin, the drone is too close or on the wrong side
    return signed_dist < margin


def check_boundary(
    pos: list,
    field: object,
    keep_clear_distance: float,
) -> bool:
    """
    Check if a position is within the field boundary (with margin).

    Args:
        pos: [x, y, z] position.
        field: Field instance with boundary_x, boundary_y, boundary_z.
        keep_clear_distance: Margin distance.

    Returns:
        True if position violates boundary, False if within bounds.
    """
    x, y, z = pos[0], pos[1], pos[2]
    m = keep_clear_distance

    if x < field.boundary_x[0] + m or x > field.boundary_x[1] - m:
        return True
    if y < field.boundary_y[0] + m or y > field.boundary_y[1] - m:
        return True
    if z < field.boundary_z[0] + m or z > field.boundary_z[1] - m:
        return True

    return False


def check_trajectory(
    samples: list,
    field: object,
    keep_clear_distance: float,
) -> list:
    """
    Check all samples of a trajectory for collisions.

    Args:
        samples: List of sample dicts, each with 'pos' (list of [x,y,z])
                 and 'segment_index' (int).
        field: Field instance.
        keep_clear_distance: Safety margin in meters.

    Returns:
        List of collision reports, each with {segment_index, sample_index, reason}.
        Empty list means no collisions found.
    """
    collisions = []

    for i, sample in enumerate(samples):
        pos = sample.get("pos", [0.0, 0.0, 0.0])
        seg_idx = sample.get("segment_index", 0)

        # Check boundary
        if check_boundary(pos, field, keep_clear_distance):
            collisions.append({
                "segment_index": seg_idx,
                "sample_index": i,
                "reason": f"Boundary violation at sample {i}: pos={pos}",
            })
            continue  # Already violated, skip obstacle checks

        # Check each obstacle
        for obs in field.obstacles:
            if check_sample(pos, obs, keep_clear_distance):
                collisions.append({
                    "segment_index": seg_idx,
                    "sample_index": i,
                    "obstacle_id": obs.get("id", "?"),
                    "obstacle_label": obs.get("label", ""),
                    "reason": (
                        f"Collision with obstacle {obs.get('id', '?')} "
                        f"({obs.get('label', obs.get('type', '?'))}) "
                        f"at sample {i}: pos=({pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f})"
                    ),
                })
                break  # One collision per sample is enough

    return collisions
