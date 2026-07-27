"""
StaticFiles 挂载 — 必须挂在所有 /api 和 /ws 之后。
"""
from fastapi.staticfiles import StaticFiles

FRONTEND_DIR = "frontend"


def mount_static(app):
    """
    挂载前端静态文件到 /。
    必须在所有 /api/* 和 /ws 路由之后调用。
    """
    import os
    if os.path.isdir(FRONTEND_DIR):
        app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")
