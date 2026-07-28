"""
后端 B 生命周期 — 启动 N 步 + 关停序列。
线程模型: rospy 主 + 目标点 + uplink + monitor + ipc (先导除 ipc 外为空壳)。
"""

import sys
import time
import signal
import logging
import threading

from config_loader import load_field, load_constraints
from state import BState
from bus import registry as bus_registry
from bus.router import call as bus_call
from ipc.client import IpcClient
from ipc.dispatch import Dispatch

logger = logging.getLogger(__name__)

_keep_running = True


def _signal_handler(sig, frame):
    global _keep_running
    logger.info(f"[lifecycle] received signal {sig}, shutting down...")
    _keep_running = False


class Lifecycle:
    """后端 B 的启动/运行/关停。"""

    def __init__(self, config_dir: str = "config"):
        self.config_dir = config_dir
        self.state: BState | None = None
        self.ipc_client: IpcClient | None = None
        self.dispatch: Dispatch | None = None
        self._threads: list[threading.Thread] = []

    def run(self):
        """主入口 — 启动并阻塞直到关停。"""
        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)

        logger.info("[lifecycle] === Backend-B starting ===")

        # 1. Load config
        field = load_field(f"{self.config_dir}/field.yaml")
        constraints = load_constraints(f"{self.config_dir}/default_constraints.yaml")
        logger.info("[lifecycle] config loaded")

        # 2. Create state
        self.state = BState(field, constraints)

        # 3. Init B bus registry (small_model/monitor 先导 stub)
        self._init_bus()

        # 4. Init IPC client
        self.ipc_client = IpcClient(self.state)
        self.dispatch = Dispatch(self.state, self.ipc_client)
        self.ipc_client.set_frame_handler(self.dispatch.handle_incoming)

        # 5. Connect to A
        if not self.ipc_client.connect():
            logger.warning("[lifecycle] initial connect to A failed, will retry in recv loop")

        # 6. Start threads
        self._start_threads()

        # 7. Main loop — wait for shutdown
        logger.info("[lifecycle] Backend-B running, Ctrl+C to stop")
        while _keep_running:
            time.sleep(0.5)

        # 8. Shutdown
        self._shutdown()
        logger.info("[lifecycle] Backend-B stopped")

    def _init_bus(self):
        """初始化 B 内总线。先导仅注册 stubs; 阶段F 接真正的 small_model/monitor。"""
        from bus.registry import init_registry

        # 先导空壳组件 (会被阶段F 替换)
        # 注意: 空壳不会驱动物理无人机 (阶段E/F 前无 setpoint 链路),
        # 但 abort/hover 等安全指令必须做有意义的兜底 (状态标记 + 日志)。
        # 阶段F 将替换为独立文件 backend-B/small_model/component.py
        class _StubSmallModel:
            def __init__(self, bstate_ref):
                self._state = bstate_ref

            def handle(self, tool, args):
                if tool == "hover":
                    self._state.small_model_status = "hovering"
                    logger.info("[lifecycle:stub] hover — maintaining current position")
                    return {"status": "ok", "action": "hover"}
                elif tool == "abort":
                    self._state.small_model_status = "idle"
                    self._state.current_action_plan = None
                    self._state.current_action_index = 0
                    logger.warning("[lifecycle:stub] abort — clearing action plan, hovering")
                    return {"status": "ok", "action": "abort"}
                elif tool == "generate_goal":
                    logger.warning("[lifecycle:stub] generate_goal called before stage F — no setpoint will be produced")
                    return {"status": "error", "reason": "small_model not yet implemented (stage F pending)"}
                else:
                    logger.warning(f"[lifecycle:stub] unknown tool={tool}")
                    return {"status": "error", "reason": f"unknown tool: {tool}"}

        class _StubMonitor:
            def handle(self, tool, args):
                return {"status": "ok", "note": "monitor not yet active (stage I pending)"}

        init_registry(_StubSmallModel(self.state), _StubMonitor())
        logger.info("[lifecycle] bus registry initialized (stub — stage F small_model / stage I monitor pending)")

    def _start_threads(self):
        """启动各工作线程。先导阶段只启动 IPC recv; 阶段F 加 uplink/goal/monitor。"""
        # IPC recv thread
        t_ipc = threading.Thread(
            target=self.ipc_client.recv_loop,
            name="ipc-recv",
            daemon=True,
        )
        t_ipc.start()
        self._threads.append(t_ipc)
        logger.info("[lifecycle] IPC recv thread started")

    def _shutdown(self):
        """关停: hover → stop publisher → rospy shutdown → close socket。"""
        logger.info("[lifecycle] shutting down...")

        # 先下发 hover (若 small_model 已就绪)
        try:
            bus_call(to="small_model", tool="hover", args={})
        except Exception as e:
            logger.warning(f"[lifecycle] hover on shutdown failed: {e}")

        # 关 IPC
        if self.ipc_client:
            self.ipc_client.close()

        # 等线程退出
        for t in self._threads:
            t.join(timeout=2.0)

        logger.info("[lifecycle] shutdown complete")
