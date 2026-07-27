"""
配置加载器 — 校验 field.yaml + default_constraints.yaml, 失败即退出。
"""
import os
import sys
import yaml


def _load_yaml(path: str) -> dict:
    if not os.path.isfile(path):
        print(f"[config_loader] FATAL: missing {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, "r") as f:
        data = yaml.safe_load(f)
    if data is None:
        print(f"[config_loader] FATAL: empty or invalid YAML: {path}", file=sys.stderr)
        sys.exit(1)
    return data


def load_field(path: str) -> dict:
    """加载场地配置, 校验必有字段 home + boundary。"""
    cfg = _load_yaml(path)

    if "boundary" not in cfg:
        print("[config_loader] FATAL: field.yaml missing 'boundary'", file=sys.stderr)
        sys.exit(1)
    b = cfg["boundary"]
    for axis in ("x", "y", "z"):
        if axis not in b or len(b[axis]) != 2:
            print(f"[config_loader] FATAL: field.yaml boundary.{axis} must be [min, max]", file=sys.stderr)
            sys.exit(1)

    if "home" not in cfg:
        print("[config_loader] FATAL: field.yaml missing 'home'", file=sys.stderr)
        sys.exit(1)
    h = cfg["home"]
    if "position" not in h or len(h["position"]) != 3:
        print("[config_loader] FATAL: field.yaml home.position must be [x, y, z]", file=sys.stderr)
        sys.exit(1)

    return cfg


def load_constraints(path: str) -> dict:
    """加载默认约束, 校验 global 字段。"""
    cfg = _load_yaml(path)

    if "global" not in cfg:
        print("[config_loader] FATAL: default_constraints.yaml missing 'global'", file=sys.stderr)
        sys.exit(1)

    g = cfg["global"]
    required = ["speed_max", "accel_max", "angular_velocity_max", "ceiling", "floor"]
    for key in required:
        if key not in g:
            print(f"[config_loader] FATAL: default_constraints.yaml global.{key} missing", file=sys.stderr)
            sys.exit(1)

    return cfg
