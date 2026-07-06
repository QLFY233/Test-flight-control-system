"""
Translator: converts a TrajectorySpec (from Backend A) into the solver's
internal TrajectoryPlan representation.

A TrajectorySpec is a dict from A:
{
    "task_id": "...",
    "segments": [
        {
            "from": {"x": ..., "y": ..., "z": ..., "yaw": ...},
            "to": {"x": ..., "y": ..., "z": ..., "yaw": ...},
            "constraints": {...},      # optional per-waypoint constraints
            "segment_constraints": {...},  # optional per-segment constraints
        },
        ...
    ],
    "global_constraints": {...},  # optional trajectory-level overrides
}
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TrajectoryPlan:
    """
    Internal representation of a planned trajectory.

    Contains segments (waypoint pairs) and constraints for the solver
    to generate a continuous trajectory from.
    """
    task_id: str
    segments: list
    global_constraints: dict = field(default_factory=dict)

    def has_remaining(self) -> bool:
        """Return True if there are un-executed segments."""
        return len(self.segments) > 0

    def next_segment(self) -> Optional[dict]:
        """
        Return the next segment without removing it, or None.
        """
        if self.segments:
            return self.segments[0]
        return None

    def pop_segment(self) -> Optional[dict]:
        """
        Remove and return the next segment, or None.
        """
        if self.segments:
            return self.segments.pop(0)
        return None

    def segment_count(self) -> int:
        return len(self.segments)


def translate_spec(
    spec: dict,
    default_constraints: dict,
) -> TrajectoryPlan:
    """
    Translate a TrajectorySpec dict from Backend A into a TrajectoryPlan.

    Performs basic validation:
    - task_id must be present and non-empty
    - segments must be a non-empty list
    - Each segment must have 'from' and 'to' fields with x,y,z
    - Unknown fields are passed through to the segment

    Args:
        spec: Raw TrajectorySpec dict from A via IPC.
        default_constraints: System default constraint values.

    Returns:
        TrajectoryPlan ready for trajectory generation.

    Raises:
        ValueError: If the spec is invalid.
    """
    task_id = spec.get("task_id", "")
    if not task_id:
        raise ValueError("TrajectorySpec missing 'task_id'")

    raw_segments = spec.get("segments", [])
    if not raw_segments:
        raise ValueError(f"TrajectorySpec '{task_id}' has no segments")

    segments = []
    for i, seg in enumerate(raw_segments):
        validated = _validate_segment(seg, i, task_id)
        segments.append(validated)

    global_constraints = spec.get("global_constraints", {})
    # Merge null global_constraints with defaults
    if not global_constraints:
        global_constraints = {}

    return TrajectoryPlan(
        task_id=task_id,
        segments=segments,
        global_constraints=global_constraints,
    )


def _validate_segment(seg: dict, index: int, task_id: str) -> dict:
    """Validate and normalize a single segment dict."""
    if not isinstance(seg, dict):
        raise ValueError(
            f"Segment {index} in '{task_id}' is not a dict: got {type(seg).__name__}"
        )

    # Validate 'from'
    from_wp = seg.get("from")
    if not isinstance(from_wp, dict):
        raise ValueError(
            f"Segment {index} in '{task_id}' missing 'from' waypoint"
        )
    _validate_waypoint(from_wp, "from", index, task_id)

    # Validate 'to'
    to_wp = seg.get("to")
    if not isinstance(to_wp, dict):
        raise ValueError(
            f"Segment {index} in '{task_id}' missing 'to' waypoint"
        )
    _validate_waypoint(to_wp, "to", index, task_id)

    # Build normalized segment
    normalized = {
        "from": {
            "x": float(from_wp["x"]),
            "y": float(from_wp["y"]),
            "z": float(from_wp["z"]),
            "yaw": float(from_wp.get("yaw", 0.0)),
        },
        "to": {
            "x": float(to_wp["x"]),
            "y": float(to_wp["y"]),
            "z": float(to_wp["z"]),
            "yaw": float(to_wp.get("yaw", 0.0)),
        },
    }

    # Optional per-point constraints (highest priority)
    if "constraints" in seg:
        normalized["constraints"] = seg["constraints"]

    # Optional per-segment constraints
    if "segment_constraints" in seg:
        normalized["segment_constraints"] = seg["segment_constraints"]

    return normalized


def _validate_waypoint(wp: dict, role: str, seg_idx: int, task_id: str) -> None:
    """Validate a waypoint has required x,y,z fields."""
    for key in ("x", "y", "z"):
        if key not in wp:
            raise ValueError(
                f"Segment {seg_idx} '{role}' waypoint in '{task_id}' "
                f"missing required field '{key}'"
            )
