"""
Field model for the solver.

Represents the operation field with boundary, home position, and obstacles.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Field:
    """Operation field model used by solver for collision detection."""
    boundary_x: tuple  # (min_x, max_x)
    boundary_y: tuple  # (min_y, max_y)
    boundary_z: tuple  # (min_z, max_z)
    home: list         # [x, y, z]
    home_yaw: float    # radians
    obstacles: list = field(default_factory=list)

    @classmethod
    def from_config(cls, cfg) -> "Field":
        """
        Create a Field from a Config object (from config_loader.py).

        Args:
            cfg: Config instance with cfg.field attribute.

        Returns:
            Field instance.
        """
        from backend_B.config_loader import Config
        if isinstance(cfg, Config):
            fc = cfg.field
        else:
            fc = cfg

        return cls(
            boundary_x=fc.boundary.x,
            boundary_y=fc.boundary.y,
            boundary_z=fc.boundary.z,
            home=list(fc.home.position),
            home_yaw=fc.home.yaw,
            obstacles=_obstacles_from_config(fc.obstacles),
        )

    @property
    def x_limits(self) -> tuple:
        return self.boundary_x

    @property
    def y_limits(self) -> tuple:
        return self.boundary_y

    @property
    def z_limits(self) -> tuple:
        return self.boundary_z


def _obstacles_from_config(obstacle_configs: list) -> list:
    """Convert ObstacleConfig objects to solver-friendly obstacle dicts."""
    obstacles = []
    for obs in obstacle_configs:
        d = {
            "id": obs.id,
            "type": obs.type,
            "label": obs.label,
        }

        if obs.type == "box":
            d["center"] = list(obs.center)
            d["size"] = list(obs.size) if obs.size else [1.0, 1.0, 1.0]

        elif obs.type == "cylinder":
            d["center"] = list(obs.center)
            d["radius"] = obs.radius if obs.radius is not None else 0.3
            d["height"] = obs.height if obs.height is not None else 3.0

        elif obs.type == "sphere":
            d["center"] = list(obs.center)
            d["radius"] = obs.radius if obs.radius is not None else 0.3

        elif obs.type == "plane":
            d["point"] = list(obs.point) if obs.point else [0.0, 0.0, 0.0]
            d["normal"] = list(obs.normal) if obs.normal else [0.0, 0.0, 1.0]

        else:
            # Unknown type: treat as sphere for safety
            d["center"] = list(obs.center) if obs.center else [0.0, 0.0, 0.0]
            d["radius"] = obs.radius if obs.radius is not None else 0.5

        obstacles.append(d)

    return obstacles
