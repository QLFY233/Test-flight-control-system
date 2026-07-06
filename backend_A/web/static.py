"""Static file mount — serves the frontend directory."""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


def mount_static(app: FastAPI) -> None:
    """Mount the frontend directory as static files at / (catch-all)."""
    app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
