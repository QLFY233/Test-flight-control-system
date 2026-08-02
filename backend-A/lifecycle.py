"""
A 侧生命周期 — 启动 9 步 + 关停, 被 main.py lifespan 调用。
"""
import logging

from config_loader import load_config
from state import AppState
from bus import registry as bus_registry
from bus.bridge import set_state as bridge_set_state
from bus.bridge import set_telemetry_buffer
from ipc.server import IpcServer
from db.session import create_all as db_create_all
from db.session import async_session as db_session_factory
from db.repos import TelemetryBuffer

logger = logging.getLogger(__name__)


class Lifecycle:
    """后端 A 启动/关停。"""

    def __init__(self, config_dir: str = "config"):
        self.config_dir = config_dir
        self.state: AppState | None = None
        self.ipc_server: IpcServer | None = None
        self.tel_buffer: TelemetryBuffer | None = None
        self._alpha_loop = None
        self._beta_agent = None

    async def startup(self):
        """FastAPI lifespan startup。"""
        logger.info("[lifecycle] === Backend-A starting (stage H) ===")

        # 1. Load config
        config = load_config(self.config_dir)
        logger.info(f"[lifecycle] config loaded, alpha_period={config.alpha_loop_period}s")

        # 2. Create AppState
        self.state = AppState(config)
        bridge_set_state(self.state)

        # 3. Init DB
        await db_create_all()
        logger.info("[lifecycle] DB initialized")

        # 4. Init A bus registry
        bus_registry.init_registry()
        logger.info("[lifecycle] bus registry initialized")

        # 5. Start TelemetryBuffer
        self.tel_buffer = TelemetryBuffer()
        await self.tel_buffer.start()
        set_telemetry_buffer(self.tel_buffer)
        logger.info("[lifecycle] TelemetryBuffer started")

        # 6. Start IPC server (A↔B bridge)
        self.ipc_server = IpcServer(self.state)
        await self.ipc_server.start()
        logger.info("[lifecycle] IPC server started")

        # 7. Start α Agent loop (阶段G)
        await self._start_alpha()

        # 8. Create β Agent (阶段H)
        await self._start_beta()

        # 9. Wire web context (阶段H)
        self._init_web_context()

        logger.info("[lifecycle] Backend-A ready (stage H)")

    async def _start_alpha(self):
        """创建并启动 α loop。"""
        try:
            from agents.alpha import make_translator, AlphaLoop
            translator = make_translator()
            self._alpha_loop = AlphaLoop(self.state, translator)
            from bus.bridge import set_alpha_loop
            set_alpha_loop(self._alpha_loop)
            await self._alpha_loop.start()
        except Exception as e:
            # I7: 缺 API key/未配置 provider 属可降级场景 (LLM 调用失败 → hover 兜底);
            #     其余异常 (import/接线错误) fail-fast, 避免静默带病启动
            msg = str(e)
            if "api_key" in msg.lower() or "not set" in msg or "API key" in msg:
                logger.warning(f"[lifecycle] α agent degraded (LLM unavailable): {e}")
                return
            logger.exception(f"[lifecycle] α agent startup failed: {e}")
            raise

    async def _start_beta(self):
        """创建 β Agent 并注入 SSE handler。"""
        try:
            from agents.beta import create_beta_agent
            self._beta_agent = create_beta_agent()
            from web.sse import set_beta_agent
            set_beta_agent(self._beta_agent)
            logger.info("[lifecycle] β agent created")
        except Exception as e:
            # I7: 缺 API key/未配置 provider 属可降级场景 (β 降级后 SSE 聊天不可用, 其余链路不受影响);
            #     其余异常 (import/接线错误) fail-fast, 避免静默带病启动
            msg = str(e)
            if "api_key" in msg.lower() or "not set" in msg or "API key" in msg:
                logger.warning(f"[lifecycle] β agent degraded (LLM unavailable): {e}")
                return
            logger.exception(f"[lifecycle] β agent startup failed: {e}")
            raise

    def _init_web_context(self):
        """注入 REST/WS 上下文依赖。"""
        try:
            # REST routes 需要 state + db
            from web.routes import set_rest_context
            set_rest_context(self.state, db_session_factory)

            # WS 需要 state
            from web.ws import set_ws_context
            set_ws_context(self.state)

            # β tools 需要 state + bus + db
            from tools.beta_tools import set_tool_context
            from bus.router import call as bus_call
            set_tool_context(self.state, bus_call, db_session_factory)

            # Bridge pose/alert/reject → WS broadcast
            from bus.bridge import set_ws_broadcast
            from web.ws import (
                broadcast_pose, broadcast_alert, broadcast_status,
                broadcast_reject, broadcast_link_status,
            )
            set_ws_broadcast(
                broadcast_pose, broadcast_alert, broadcast_status,
                broadcast_reject, broadcast_link_status,
            )

            logger.info("[lifecycle] web context wired (REST/WS/SSE/tools)")
        except Exception as e:
            # I7: fail-fast — DB 路由/WS 依赖此注入, 失败继续会导致全量 500
            logger.exception(f"[lifecycle] web context wiring failed: {e}")
            raise

    async def shutdown(self):
        """FastAPI lifespan shutdown。"""
        logger.info("[lifecycle] shutting down...")

        # 停 α loop
        if self._alpha_loop:
            await self._alpha_loop.stop()

        # 关 IPC
        if self.ipc_server:
            await self.ipc_server.stop()

        # 关 TelemetryBuffer
        if self.tel_buffer:
            await self.tel_buffer.stop()

        logger.info("[lifecycle] Backend-A stopped")
