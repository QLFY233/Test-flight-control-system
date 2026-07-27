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

    # REST routes (先导 stub)
    @app.get("/api/health")
    async def health():
        return {"status": "ok", "backend": "A"}

    # StaticFiles — 必须在所有 /api/* 和 /ws 之后挂载
    from web.static import mount_static
    mount_static(app)

    return app


def main():
    parser = argparse.ArgumentParser(description="后端 A — Agent 中枢")
    parser.add_argument("--config-dir", default="config", help="配置文件目录")
    parser.add_argument("--port", default=8000, type=int, help="HTTP 端口")
    parser.add_argument("--host", default="0.0.0.0", help="绑定地址")
    args = parser.parse_args()

    import uvicorn
    app = create_app(config_dir=args.config_dir)
    logger.info(f"[main] starting uvicorn on {args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
