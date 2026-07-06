"""FastAPI application entry point with Uvicorn.

Creates the FastAPI app with lifespan, registers all routes,
WebSocket endpoint, and static file mount.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load .env before anything else
load_dotenv()

# Ensure project root is on sys.path so backend_A imports work
_proj_root = Path(__file__).resolve().parent.parent
if str(_proj_root) not in sys.path:
    sys.path.insert(0, str(_proj_root))

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Global references (set during lifespan)
# ---------------------------------------------------------------------------
_app_state = None
_config = None
_bus_router = None
_bridge = None
_beta_agent = None
_ipc_server = None
_alpha_task = None
_telemetry_task = None


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown."""
    global _app_state, _config, _bus_router, _bridge
    global _beta_agent, _ipc_server, _alpha_task, _telemetry_task

    # ---- STARTUP ----
    logger.info("=" * 60)
    logger.info("Flight Control System — Backend A (Agent Hub)")
    logger.info("=" * 60)

    # Load config
    from backend_A.config_loader import load_config, Config
    _config = load_config()

    # Init AppState
    from backend_A.state import AppState
    _app_state = AppState(config=_config)

    # Init bus
    from backend_A.bus.registry import register
    from backend_A.bus.router import set_bridge as router_set_bridge
    from backend_A.bus.bridge import Bridge
    from backend_A.bus import router as bus_router_module

    _bridge = Bridge()
    _bridge.set_app_state(_app_state)
    router_set_bridge(_bridge)
    _bus_router = bus_router_module

    # Init monitor trigger
    from backend_A.monitor_trigger.trigger import AlertHandler
    alert_handler = AlertHandler(_app_state)
    _bridge.set_monitor_trigger(alert_handler)
    register("monitor_trigger", alert_handler, tools=["alert"])

    # Init web routes
    from backend_A.web.routes import init_routes
    init_routes(_app_state, _config, _bus_router)

    from backend_A.web.sse import init_sse

    from backend_A.web.ws import init_ws
    init_ws(_app_state, _bus_router)

    # Run startup sequence
    from backend_A.lifecycle import startup
    refs = await startup(
        app_state=_app_state,
        config=_config,
        bus_router=_bus_router,
        bridge=_bridge,
    )

    _beta_agent = refs["beta_agent"]
    _ipc_server = refs["ipc_server"]
    _alpha_task = refs["alpha_task"]
    _telemetry_task = refs["telemetry_task"]

    # Init SSE with beta agent
    init_sse(_app_state, _beta_agent, _bus_router)

    # Register beta tools with beta agent
    from backend_A.tools.beta_tools import init_tools, get_all_tools
    from backend_A.db.session import AsyncSessionLocal
    init_tools(_app_state, AsyncSessionLocal, _bus_router, _config)

    logger.info("Backend A is ready.")

    yield

    # ---- SHUTDOWN ----
    from backend_A.lifecycle import shutdown
    await shutdown(
        app_state=_app_state,
        bus_router=_bus_router,
        bridge=_bridge,
        ipc_server=_ipc_server,
        alpha_task=_alpha_task,
        telemetry_task=_telemetry_task,
    )

    logger.info("Backend A stopped.")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Flight Control System — Agent Hub",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS (allow frontend dev server)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register REST routes
    from backend_A.web.routes import router as rest_router
    app.include_router(rest_router)

    # Register SSE routes
    from backend_A.web.sse import router as sse_router
    app.include_router(sse_router)

    # Register WebSocket routes
    from backend_A.web.ws import router as ws_router
    app.include_router(ws_router)

    # Mount static files (must be last)
    from backend_A.web.static import mount_static
    # Only mount if frontend directory exists
    frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
    if frontend_dir.is_dir():
        mount_static(app)
    else:
        logger.warning(f"Frontend directory not found at {frontend_dir}, skipping static mount")

    return app


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Uvicorn entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))

    app = create_app()
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
