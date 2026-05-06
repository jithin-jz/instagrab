"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from app.lifespan import lifespan
from app.routers import health, instagram, telegram


def create_app() -> FastAPI:
    """Build the FastAPI application with all routers attached."""
    app = FastAPI(
        title="Instagram → Telegram Delivery Bot",
        description=(
            "Receives Instagram mention webhooks, downloads the tagged media, "
            "and forwards it privately to the registered Telegram user."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )
    app.include_router(health.router)
    app.include_router(instagram.router)
    app.include_router(telegram.router)
    return app


app = create_app()
