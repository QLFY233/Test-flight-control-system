"""Configuration loader with Pydantic validation.

Reads config/field.yaml and config/default_constraints.yaml from the project root.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field as PydField, field_validator


# ---------------------------------------------------------------------------
# Pydantic models for field.yaml
# ---------------------------------------------------------------------------

class FieldBoundary(BaseModel):
    x: list[float]  # [min, max]
    y: list[float]
    z: list[float]

    @field_validator("x", "y", "z")
    @classmethod
    def _pair(cls, v: list[float]) -> list[float]:
        if len(v) != 2:
            raise ValueError(f"boundary must be [min, max], got {v}")
        return v


class HomeConfig(BaseModel):
    position: list[float]  # [x, y, z]
    yaw: float = 0.0


class ObstacleConfig(BaseModel):
    id: int
    type: str  # box / cylinder / sphere / plane
    center: Optional[list[float]] = None
    size: Optional[list[float]] = None
    radius: Optional[float] = None
    height: Optional[float] = None
    point: Optional[list[float]] = None
    normal: Optional[list[float]] = None
    label: str = ""


class FieldConfig(BaseModel):
    boundary: FieldBoundary
    home: HomeConfig
    obstacles: list[ObstacleConfig] = PydField(default_factory=list)


# ---------------------------------------------------------------------------
# Pydantic models for default_constraints.yaml
# ---------------------------------------------------------------------------

class GlobalConstraints(BaseModel):
    speed_max: float = 1.5
    accel_max: float = 2.0
    angular_velocity_max: float = 0.5
    keep_clear_distance: float = 0.5
    ceiling: float = 2.5
    floor: float = 0.3


class PresetConstraints(BaseModel):
    speed_max: float
    accel_max: float
    keep_clear_distance: float


class DefaultConstraints(BaseModel):
    global_: GlobalConstraints = PydField(alias="global")
    presets: dict[str, PresetConstraints] = PydField(default_factory=dict)


# ---------------------------------------------------------------------------
# Unified Config dataclass
# ---------------------------------------------------------------------------

@dataclass
class Config:
    field: FieldConfig
    constraints: DefaultConstraints
    alpha_loop_period: float = 2.0
    alpha_history_rounds: int = 10
    project_root: Path = field(default_factory=lambda: Path.cwd())


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def _find_project_root() -> Path:
    """Walk upward from this file to find the repo root (contains config/)."""
    p = Path(__file__).resolve().parent.parent  # backend-A -> repo root
    if not (p / "config").is_dir():
        # fallback: walk up
        for parent in Path(__file__).resolve().parents:
            if (parent / "config").is_dir():
                return parent
    return p


def load_config(project_root: Optional[Path] = None) -> Config:
    """Load field.yaml and default_constraints.yaml, validate, return Config."""
    root = project_root or _find_project_root()
    config_dir = root / "config"

    field_path = config_dir / "field.yaml"
    constraints_path = config_dir / "default_constraints.yaml"

    if not field_path.exists():
        raise FileNotFoundError(f"Missing config file: {field_path}")
    if not constraints_path.exists():
        raise FileNotFoundError(f"Missing config file: {constraints_path}")

    with open(field_path, "r", encoding="utf-8") as f:
        field_data = yaml.safe_load(f)
    with open(constraints_path, "r", encoding="utf-8") as f:
        constraints_data = yaml.safe_load(f)

    field = FieldConfig(**field_data)
    constraints = DefaultConstraints(**constraints_data)

    alpha_loop_period = float(os.environ.get("ALPHA_LOOP_PERIOD", "2.0"))
    alpha_history_rounds = int(os.environ.get("ALPHA_HISTORY_ROUNDS", "10"))

    return Config(
        field=field,
        constraints=constraints,
        alpha_loop_period=alpha_loop_period,
        alpha_history_rounds=alpha_history_rounds,
        project_root=root,
    )
