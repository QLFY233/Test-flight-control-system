"""
后端 A 入口 — Agent 中枢 (Python 3.10, FastAPI + Uvicorn)。
用法: python -m backend_A.main [--config-dir config] [--port 8000]
"""
import sys
import os
import argparse
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

# 确保 backend-A/ 在 Python path 中
_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Lifecycle singleton
_lifecycle = None


def get_state():
    """获取 AppState (供 web 路由使用)。"""
    if _lifecycle is None:
        return None
    return _lifecycle.state


def get_lifecycle():
    return _lifecycle


def create_app(config_dir: str = "config") -> FastAPI:
    global _lifecycle

    from lifecycle import Lifecycle
    lc = Lifecycle(config_dir=config_dir)
    _lifecycle = lc

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await lc.startup()
        yield
        await lc.shutdown()

    app = FastAPI(title="试飞控制系统 — Backend A", lifespan=lifespan)

    # S1: dev 流程 (CLAUDE.md §4.3: frontend :3456 http.server) 跨域白名单;
    # 生产同源 (StaticFiles 挂 /) 不受影响
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3456",
            "http://127.0.0.1:3456",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # SSE (β Chat) — 先于 StaticFiles
    from web.sse import router as sse_router
    app.include_router(sse_router)

    # REST routes — 先于 StaticFiles
    from web.routes import router as rest_router
    app.include_router(rest_router)

    # WebSocket — 先于 StaticFiles
    from web.ws import router as ws_router
    app.include_router(ws_router)

    # StaticFiles — 必须在所有 /api/* 和 /ws 之后挂载
    from web.static import mount_static
    mount_static(app)

    return app


def main():
    parser = argparse.ArgumentParser(description="后端 A — Agent 中枢")
    parser.add_argument("--config-dir", default="config", help="配置文件目录")
    parser.add_argument("--port", default=8000, type=int, help="HTTP 端口")
    # I8: 默认绑定回环地址 (防局域网任意对端触发飞控指令); 远程访问设 BACKEND_A_HOST=0.0.0.0
    parser.add_argument(
        "--host",
        default=os.environ.get("BACKEND_A_HOST", "127.0.0.1"),
        help="绑定地址 (默认 127.0.0.1)",
    )
    args = parser.parse_args()

    import uvicorn
    app = create_app(config_dir=args.config_dir)
    logger.info(f"[main] starting uvicorn on {args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
