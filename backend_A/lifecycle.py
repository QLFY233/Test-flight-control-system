"""Application lifecycle — startup and shutdown procedures.

Startup (9 steps):
1. Load config (Pydantic validation) → Config singleton
2. Initialize SQLAlchemy engine + session factory
3. create_all() tables
4. Initialize AppState (dataclass + Lock)
5. Initialize alpha/beta agents (read prompts, register beta tools)
6. Start A↔B IPC server (listen on Unix socket)
7. Start alpha loop background asyncio Task
8. Start heartbeat (2s ping)
9. Begin accepting frontend requests

Shutdown (6 steps):
1. Stop accepting new requests
2. Cancel alpha loop task (wait for current cycle)
3. Send hover to B via IPC (safe hover)
4. Close IPC (notify B)
5. Close SQLAlchemy engine
6. Clean up resources
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


async def startup(
    app_state,
    config,
    bus_router,
    bridge,
) -> dict:
    """Run startup sequence. Returns references needed by the application."""
    logger.info("=" * 60)
    logger.info("lifecycle: STARTUP (9 steps)")
    logger.info("=" * 60)

    # Step 1: Config already loaded (passed in)
    logger.info("[1/9] Config loaded OK")
    logger.info(f"  field: {config.field.boundary.x} x {config.field.boundary.y} x {config.field.boundary.z}")
    logger.info(f"  obstacles: {len(config.field.obstacles)}")
    logger.info(f"  alpha_loop_period: {config.alpha_loop_period}s")

    # Step 2: Initialize database engine + session factory
    logger.info("[2/9] Initializing database engine...")
    from backend_A.db.session import engine, AsyncSessionLocal, create_all

    # Step 3: Create tables
    logger.info("[3/9] Creating database tables...")
    await create_all()

    # Step 4: AppState already created (passed in)
    logger.info("[4/9] AppState initialized OK")

    # Step 5: Initialize agents
    logger.info("[5/9] Initializing alpha/beta agents...")
    from backend_A.agents.llm import make_agent
    from backend_A.tools.beta_tools import init_tools, get_all_tools
    from backend_A.bus.registry import register

    # Initialize beta tools
    init_tools(app_state, AsyncSessionLocal, bus_router, config)

    # Load beta prompt
    beta_prompt_path = Path(__file__).resolve().parent / "prompts" / "beta.md"
    if beta_prompt_path.exists():
        beta_instructions = beta_prompt_path.read_text(encoding="utf-8")
    else:
        beta_instructions = "You are Beta, the central scheduler agent for a flight control system."

    # Create beta agent with tools
    beta_tools = get_all_tools()
    beta_agent = make_agent(instructions=beta_instructions, tools=beta_tools)
    register("beta", beta_agent, tools=["chat"])

    # Alpha agent is created inside alpha_loop (has its own instructions)
    logger.info(f"  beta agent created with {len(beta_tools)} tools")
    logger.info(f"  alpha agent will be created in alpha loop")

    # Step 6: Start IPC server
    logger.info("[6/9] Starting IPC server...")
    from backend_A.ipc.server import IPCServer
    ipc_server = IPCServer(bridge, app_state)
    await ipc_server.start()

    # Step 7: Start alpha loop
    logger.info("[7/9] Starting alpha loop...")
    from backend_A.agents.alpha import start_alpha_loop
    alpha_task = start_alpha_loop(app_state, bus_router)

    # Step 8: Start heartbeat (already handled by IPC server's heartbeat loop)
    logger.info("[8/9] Heartbeat running (2s ping via IPC server)")

    # Step 8b: Start telemetry buffer flush
    logger.info("[8b/9] Starting telemetry buffer flush...")
    from backend_A.db.repos import flush_telemetry_buffer
    telemetry_task = asyncio.create_task(
        flush_telemetry_buffer(app_state, AsyncSessionLocal)
    )

    # Step 9: Ready
    logger.info("[9/9] Ready to accept requests")
    logger.info("=" * 60)

    return {
        "beta_agent": beta_agent,
        "ipc_server": ipc_server,
        "alpha_task": alpha_task,
        "telemetry_task": telemetry_task,
    }


async def shutdown(
    app_state,
    bus_router,
    bridge,
    ipc_server,
    alpha_task: Optional[asyncio.Task] = None,
    telemetry_task: Optional[asyncio.Task] = None,
) -> None:
    """Run shutdown sequence (6 steps)."""
    logger.info("=" * 60)
    logger.info("lifecycle: SHUTDOWN (6 steps)")
    logger.info("=" * 60)

    # Step 1: Stop accepting new requests (handled by FastAPI)
    logger.info("[1/6] Stopped accepting new requests")

    # Step 2: Cancel alpha loop
    logger.info("[2/6] Cancelling alpha loop...")
    if alpha_task:
        alpha_task.cancel()
        try:
            await alpha_task
        except asyncio.CancelledError:
            pass

    # Cancel telemetry flush
    if telemetry_task:
        telemetry_task.cancel()
        try:
            await telemetry_task
        except asyncio.CancelledError:
            pass

    # Step 3: Send hover to B
    logger.info("[3/6] Sending hover to B...")
    try:
        await bus_router.call(to="solver", tool="hover", args={})
    except Exception as exc:
        logger.warning(f"  hover send failed (B may already be down): {exc}")

    # Step 4: Close IPC
    logger.info("[4/6] Closing IPC server...")
    if ipc_server:
        await ipc_server.stop()

    # Step 5: Close database
    logger.info("[5/6] Closing database engine...")
    from backend_A.db.session import close_engine
    await close_engine()

    # Step 6: Clean up
    logger.info("[6/6] Clean up complete")
    logger.info("=" * 60)
