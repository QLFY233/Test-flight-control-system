from __future__ import annotations
"""
B 侧组件静态注册表。
先导注册: small_model, monitor。
ego_planner / lidar 阶段2/4 注册。
"""
from bus.protocol import TO_SMALL_MODEL, TO_MONITOR, TO_EGO_PLANNER, TO_LIDAR

_registry: dict[str, dict] = {}


def register(name: str, component, accepted_tools: list[str]):
    """注册一个组件, 声明其接受的 tool 列表。"""
    if name in _registry:
        raise ValueError(f"Component '{name}' already registered")
    _registry[name] = {"component": component, "tools": set(accepted_tools)}


def get(name: str):
    """获取组件条目。"""
    return _registry.get(name)


def get_component(name: str):
    """获取组件实现。"""
    entry = _registry.get(name)
    if entry:
        return entry["component"]
    return None


def accepts(name: str, tool: str) -> bool:
    """检查组件是否接受给定 tool。"""
    entry = _registry.get(name)
    if not entry:
        return False
    return tool in entry["tools"]


def list_components() -> list[str]:
    """列出所有已注册组件名。"""
    return list(_registry.keys())


def init_registry(small_model_component, monitor_component):
    """启动时初始化 B 侧注册表。ego_planner/lidar 阶段2/4 补注册。"""
    if small_model_component:
        register(TO_SMALL_MODEL, small_model_component, ["generate_goal", "abort", "hover"])
    if monitor_component:
        register(TO_MONITOR, monitor_component, [])  # monitor 不接受 call, 只产 event
    # 阶段2/4: 注册 ego_planner / lidar
