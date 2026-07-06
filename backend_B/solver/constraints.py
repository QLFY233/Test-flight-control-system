"""
Constraint resolution for Backend B solver.

Implements the overloaded constraint model:
  point_constraints > segment_constraints > global_constraints > defaults
"""

from typing import Optional

# All recognised constraint keys
KNOWN_KEYS = {
    "speed_max",
    "accel_max",
    "angular_velocity_max",
    "keep_clear_distance",
    "ceiling",
    "floor",
}


def resolve_constraints(
    point_c: Optional[dict] = None,
    segment_c: Optional[dict] = None,
    global_c: Optional[dict] = None,
    default_c: Optional[dict] = None,
) -> dict:
    """
    Resolve final per-point or per-segment constraints using cascade:
      point > segment > global > default

    Args:
        point_c: Per-waypoint constraint overrides (highest priority).
        segment_c: Per-segment constraint overrides.
        global_c: Trajectory-level constraint overrides.
        default_c: System default constraints (lowest priority).

    Returns:
        Merged constraint dict containing only KNOWN_KEYS.
    """
    point_c = point_c or {}
    segment_c = segment_c or {}
    global_c = global_c or {}
    default_c = default_c or {}

    merged = {}

    for key in KNOWN_KEYS:
        # Walk the cascade from highest to lowest priority
        value = _first_non_none(
            point_c.get(key),
            segment_c.get(key),
            global_c.get(key),
            default_c.get(key),
        )
        if value is not None:
            merged[key] = float(value)

    return merged


def _first_non_none(*values):
    """Return the first value that is not None."""
    for v in values:
        if v is not None:
            return v
    return None


def check_unknown_keys(constraints: dict) -> list:
    """
    Return a list of keys in `constraints` that are not in KNOWN_KEYS.
    These may be warnings but are tolerated.
    """
    return [k for k in constraints if k not in KNOWN_KEYS]


def validate_constraints(constraints: dict) -> list:
    """
    Validate resolved constraints. Returns list of error messages.

    Checks:
    - speed_max > 0
    - accel_max > 0
    - floor < ceiling
    - keep_clear_distance >= 0
    - angular_velocity_max > 0
    """
    errors = []

    if constraints.get("speed_max", 1.0) <= 0:
        errors.append("speed_max must be positive")
    if constraints.get("accel_max", 1.0) <= 0:
        errors.append("accel_max must be positive")
    if constraints.get("angular_velocity_max", 0.1) <= 0:
        errors.append("angular_velocity_max must be positive")
    if constraints.get("keep_clear_distance", 0.0) < 0:
        errors.append("keep_clear_distance must be non-negative")

    ceiling = constraints.get("ceiling", 10.0)
    floor = constraints.get("floor", 0.0)
    if floor >= ceiling:
        errors.append(f"floor ({floor}) must be less than ceiling ({ceiling})")

    return errors


def constraints_to_dict(
    speed_max: float = 1.5,
    accel_max: float = 2.0,
    angular_velocity_max: float = 0.5,
    keep_clear_distance: float = 0.5,
    ceiling: float = 2.5,
    floor: float = 0.3,
) -> dict:
    """Convenience: create a constraints dict from values."""
    return {
        "speed_max": speed_max,
        "accel_max": accel_max,
        "angular_velocity_max": angular_velocity_max,
        "keep_clear_distance": keep_clear_distance,
        "ceiling": ceiling,
        "floor": floor,
    }
