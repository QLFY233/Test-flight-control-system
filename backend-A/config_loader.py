"""
A 侧配置加载器 — 加载 field.yaml + default_constraints.yaml + 环境变量。
"""
import os
import yaml

from state import Config


def _load_yaml(path: str) -> dict:
    # S5: 库函数不再 print+exit — 抛带路径信息的异常, 由 main/调用方决定退出
    if not os.path.isfile(path):
        raise FileNotFoundError(f"[config_loader] missing config file: {path}")
    with open(path) as f:
        data = yaml.safe_load(f)
    if data is None:
        raise ValueError(f"[config_loader] empty YAML: {path}")
    return data


def load_config(config_dir: str = "config") -> Config:
    """加载全部 A 侧配置。"""
    field = _load_yaml(f"{config_dir}/field.yaml")
    constraints = _load_yaml(f"{config_dir}/default_constraints.yaml")

    # 环境变量
    alpha_period = float(os.environ.get("ALPHA_LOOP_PERIOD", "2.0"))
    alpha_rounds = int(os.environ.get("ALPHA_HISTORY_ROUNDS", "10"))

    return Config(
        alpha_loop_period=alpha_period,
        alpha_history_rounds=alpha_rounds,
        field_cfg=field,
        constraints=constraints,
    )
