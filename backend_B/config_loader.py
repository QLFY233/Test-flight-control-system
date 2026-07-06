"""
Configuration loader for Backend B.

Loads field.yaml and default_constraints.yaml without pydantic,
using pure dataclasses and PyYAML.
"""

from dataclasses import dataclass, field
from typing import Optional

import yaml


@dataclass
class FieldBoundary:
    x: tuple  # (min, max)
    y: tuple  # (min, max)
    z: tuple  # (min, max)


@dataclass
class HomeConfig:
    position: list  # [x, y, z]
    yaw: float = 0.0


@dataclass
class ObstacleConfig:
    id: int
    type: str
    center: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    size: Optional[list] = None       # box: [sx, sy, sz]
    radius: Optional[float] = None    # sphere, cylinder
    height: Optional[float] = None    # cylinder
    point: Optional[list] = None      # plane: [px, py, pz]
    normal: Optional[list] = None     # plane: [nx, ny, nz]
    label: str = ""


@dataclass
class FieldConfig:
    boundary: FieldBoundary
    home: HomeConfig
    obstacles: list  # list[ObstacleConfig]


@dataclass
class ConstraintsConfig:
    speed_max: float = 1.5
    accel_max: float = 2.0
    angular_velocity_max: float = 0.5
    keep_clear_distance: float = 0.5
    ceiling: float = 2.5
    floor: float = 0.3
    unknown: dict = field(default_factory=dict)  # passthrough for unknown keys


@dataclass
class Config:
    field: FieldConfig
    default_constraints: ConstraintsConfig
    presets: dict = field(default_factory=dict)


def load_config(
    field_path: str = "config/field.yaml",
    constraints_path: str = "config/default_constraints.yaml",
) -> Config:
    """Load field and constraints configuration from YAML files."""
    field_cfg = _load_field(field_path)
    constraints_cfg, presets = _load_constraints(constraints_path)
    return Config(
        field=field_cfg,
        default_constraints=constraints_cfg,
        presets=presets,
    )


def _load_field(path: str) -> FieldConfig:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    boundary_data = raw.get("boundary", {})
    boundary = FieldBoundary(
        x=tuple(boundary_data.get("x", [0.0, 5.0])),
        y=tuple(boundary_data.get("y", [0.0, 4.0])),
        z=tuple(boundary_data.get("z", [0.0, 3.0])),
    )

    home_data = raw.get("home", {})
    home = HomeConfig(
        position=list(home_data.get("position", [0.0, 0.0, 0.5])),
        yaw=float(home_data.get("yaw", 0.0)),
    )

    obstacles = []
    for obs_data in raw.get("obstacles", []):
        obstacles.append(ObstacleConfig(
            id=int(obs_data.get("id", 0)),
            type=str(obs_data.get("type", "box")),
            center=list(obs_data.get("center", [0.0, 0.0, 0.0])),
            size=list(obs_data["size"]) if "size" in obs_data else None,
            radius=float(obs_data["radius"]) if "radius" in obs_data else None,
            height=float(obs_data["height"]) if "height" in obs_data else None,
            point=list(obs_data["point"]) if "point" in obs_data else None,
            normal=list(obs_data["normal"]) if "normal" in obs_data else None,
            label=str(obs_data.get("label", "")),
        ))

    return FieldConfig(boundary=boundary, home=home, obstacles=obstacles)


def _load_constraints(path: str) -> tuple:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    global_data = raw.get("global", {})
    known = {
        "speed_max", "accel_max", "angular_velocity_max",
        "keep_clear_distance", "ceiling", "floor",
    }
    unknown = {k: v for k, v in global_data.items() if k not in known}

    constraints = ConstraintsConfig(
        speed_max=float(global_data.get("speed_max", 1.5)),
        accel_max=float(global_data.get("accel_max", 2.0)),
        angular_velocity_max=float(global_data.get("angular_velocity_max", 0.5)),
        keep_clear_distance=float(global_data.get("keep_clear_distance", 0.5)),
        ceiling=float(global_data.get("ceiling", 2.5)),
        floor=float(global_data.get("floor", 0.3)),
        unknown=unknown,
    )

    presets = raw.get("presets", {})
    return constraints, presets
