"""FastAPI lifespan: startup, shutdown, scheduler, and bot wiring."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
from fastapi import FastAPI

from app.concurrency import drain_background_tasks, reset_download_semaphore
from app.database import get_config, get_stats_summary, init_db
from app.logging import log_critical, log_info, log_warning
from app.scheduler import start_scheduler
from app.services.instagram_client import (
    check_token_health,
    refresh_access_token,
    sync_followers,
)
from app.services.telegram_bot import build_bot_app, set_application
from app.settings import get_settings


def _load_persisted_token() -> None:
    """Load a persisted Instagram access token into the process environment."""
    token = get_config("access_token")
    if token:
        os.environ["IG_ACCESS_TOKEN"] = token


async def _startup_token_health() -> None:
    """Log current Instagram token health during startup."""
    settings = get_settings()
    has_expiry = bool(get_config("token_expires_at"))
    has_token = bool(settings.IG_ACCESS_TOKEN or os.getenv("IG_ACCESS_TOKEN"))
    if not has_token:
        log_critical("startup", "", "IG_ACCESS_TOKEN is not configured")
        return
    if not has_expiry:
        log_warning("startup", "", "Token expiry unknown; attempting refresh")
        await refresh_access_token()
    is_valid, days = check_token_health()
    if not is_valid:
        log_critical("startup", "", "Access token is expired or expiry is unknown")
    elif days < 10:
        log_warning("startup", "", f"Token expires in {days} days")
    else:
        log_info("startup", "", f"Token valid for {days} days")


async def _startup_followers() -> None:
    """Fetch and cache followers during startup."""
    log_info("startup", "", "Syncing Instagram followers...")
    try:
        await sync_followers(force=True)
    except (RuntimeError, httpx.HTTPError) as exc:
        log_critical("startup", "", f"Initial follower sync failed: {exc}")
        return
    stats = get_stats_summary()
    log_info("startup", "", f"{stats['followers_cached']} followers cached")


async def _start_bot(bot_app) -> None:
    """Initialize the Telegram bot in webhook or polling mode."""
    settings = get_settings()
    await bot_app.initialize()
    await bot_app.start()
    if settings.use_telegram_webhook:
        webhook_url = settings.telegram_webhook_url
        await bot_app.bot.set_webhook(
            url=webhook_url,
            secret_token=settings.TG_WEBHOOK_SECRET,
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query"],
        )
        log_info("startup", "", f"Telegram webhook registered at {webhook_url}")
    else:
        await bot_app.bot.delete_webhook(drop_pending_updates=True)
        await bot_app.updater.start_polling(drop_pending_updates=True)
        log_info("startup", "", "Telegram polling started")


async def _stop_bot(bot_app) -> None:
    """Tear down the Telegram bot cleanly."""
    settings = get_settings()
    try:
        if not settings.use_telegram_webhook and bot_app.updater is not None:
            await bot_app.updater.stop()
        await bot_app.stop()
        await bot_app.shutdown()
    except Exception as exc:  # noqa: BLE001 — shutdown best-effort
        log_warning("startup", "", f"Bot shutdown error: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize and shut down the webhook server dependencies."""
    del app
    init_db()
    log_info("startup", "", "Database initialized")
    _load_persisted_token()
    await _startup_token_health()
    await _startup_followers()
    bot_app = build_bot_app()
    set_application(bot_app)
    await _start_bot(bot_app)
    scheduler = start_scheduler()
    log_info("startup", "", "🚀 System running")
    try:
        yield
    finally:
        log_info("startup", "", "Shutting down...")
        scheduler.shutdown()
        await drain_background_tasks()
        await _stop_bot(bot_app)
        set_application(None)
        reset_download_semaphore()
        log_info("startup", "", "System stopped")
