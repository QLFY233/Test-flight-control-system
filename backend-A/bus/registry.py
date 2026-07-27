"""
A 侧组件静态注册表。
先导注册: alpha, beta, fft_analyzer, stats, filter, history_query, dashboard_driver。
"""
from bus.protocol import (
    TO_ALPHA, TO_BETA,
    TO_FFT_ANALYZER, TO_STATS, TO_FILTER,
    TO_HISTORY_QUERY, TO_DASHBOARD_DRIVER,
    TO_SMALL_MODEL, TO_MONITOR,
)

# B 侧组件标识 — bridge 用
B_SIDE_COMPONENTS = {TO_SMALL_MODEL, TO_MONITOR}

_registry: dict[str, dict] = {}


def register(name: str, component, accepted_tools: list[str]):
    """注册一个组件。"""
    if name in _registry:
        raise ValueError(f"Component '{name}' already registered")
    _registry[name] = {"component": component, "tools": set(accepted_tools)}


def get(name: str):
    return _registry.get(name)


def get_component(name: str):
    entry = _registry.get(name)
    return entry["component"] if entry else None


def accepts(name: str, tool: str) -> bool:
    entry = _registry.get(name)
    if not entry:
        return False
    return tool in entry["tools"]


def is_b_side(name: str) -> bool:
    """检查组件是否在 B 侧 (需经 IPC 桥接)。"""
    return name in B_SIDE_COMPONENTS


def init_registry(
    alpha_component=None,
    beta_component=None,
    fft_component=None,
    stats_component=None,
    filter_component=None,
    history_query_component=None,
    dashboard_component=None,
):
    """启动时初始化 A 侧注册表。先导可传 None, 阶段 G/H 补。"""
    if alpha_component:
        register(TO_ALPHA, alpha_component, ["translate"])
    if beta_component:
        register(TO_BETA, beta_component, [])
    if fft_component:
        register(TO_FFT_ANALYZER, fft_component, ["fft"])
    if stats_component:
        register(TO_STATS, stats_component, ["stats"])
    if filter_component:
        register(TO_FILTER, filter_component, ["filter"])
    if history_query_component:
        register(TO_HISTORY_QUERY, history_query_component, ["query_sessions", "query_telemetry", "query_environment", "query_conversations"])
    if dashboard_component:
        register(TO_DASHBOARD_DRIVER, dashboard_component, ["dashboard_configure", "dashboard_set_filter", "dashboard_list_panels"])
