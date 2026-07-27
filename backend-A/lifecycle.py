"""
A 侧生命周期 — 启动 9 步 + 关停, 被 main.py lifespan 调用。
"""
import logging

from config_loader import load_config
from state import AppState
from bus import registry as bus_registry
from bus.bridge import set_state as bridge_set_state
from ipc.server import IpcServer
from db.session import create_all as db_create_all
from db.repos import TelemetryBuffer

logger = logging.getLogger(__name__)


class Lifecycle:
    """后端 A 启动/关停。"""

    def __init__(self, config_dir: str = "config"):
        self.config_dir = config_dir
        self.state: AppState | None = None
        self.ipc_server: IpcServer | None = None
        self.tel_buffer: TelemetryBuffer | None = None

    async def startup(self):
        """FastAPI lifespan startup。"""
        logger.info("[lifecycle] === Backend-A starting ===")

        # 1. Load config
        config = load_config(self.config_dir)
        logger.info(f"[lifecycle] config loaded, alpha_period={config.alpha_loop_period}s")

        # 2. Create AppState
        self.state = AppState(config)
        bridge_set_state(self.state)

        # 3. Init DB
        await db_create_all()
        logger.info("[lifecycle] DB initialized")

        # 4. Init A bus registry (先导 stubs, 阶段 G/H 补真实组件)
        bus_registry.init_registry()
        logger.info("[lifecycle] bus registry initialized")

        # 5. Start TelemetryBuffer
        self.tel_buffer = TelemetryBuffer()
        await self.tel_buffer.start()
        logger.info("[lifecycle] TelemetryBuffer started")

        # 6. Start IPC server
        self.ipc_server = IpcServer(self.state)
        await self.ipc_server.start()
        logger.info("[lifecycle] IPC server started")

        # 7-9: α/β/analytics (阶段 G/H)
        logger.info("[lifecycle] Backend-A ready")

    async def shutdown(self):
        """FastAPI lifespan shutdown。"""
        logger.info("[lifecycle] shutting down...")

        # 关 IPC
        if self.ipc_server:
            await self.ipc_server.stop()

        # 关 TelemetryBuffer
        if self.tel_buffer:
            await self.tel_buffer.stop()

        logger.info("[lifecycle] Backend-A stopped")
