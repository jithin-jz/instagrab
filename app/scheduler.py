"""Scheduled maintenance jobs for token refresh, followers, and cleanup."""

from __future__ import annotations

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.database import cleanup_old_data, get_followers_count
from app.logging import log_critical, log_info, log_warning
from app.services.instagram_client import (
    check_token_health,
    refresh_access_token,
    sync_followers,
)


async def job_refresh_followers() -> None:
    """Refresh the follower cache from Instagram."""
    log_info("scheduler", "", "Starting follower sync")
    old_count = get_followers_count()
    try:
        await sync_followers(force=True)
    except (RuntimeError, httpx.HTTPError) as exc:
        log_critical("scheduler", "", f"Follower sync failed: {exc}")
        return
    new_count = get_followers_count()
    log_info("scheduler", "", f"Follower sync complete: {old_count} → {new_count}")


async def job_refresh_token() -> None:
    """Refresh the Instagram long-lived access token."""
    log_info("token", "", "Starting scheduled token refresh")
    success = await refresh_access_token()
    if not success:
        log_critical("token", "", "Token refresh failed")
        return
    log_info("token", "", "Token refreshed successfully")


async def job_token_health_check() -> None:
    """Check token expiry and alert the admin before it becomes unsafe."""
    _, days = check_token_health()
    if days < 10:
        await _send_token_warning(days)
        log_warning("token", "", f"Token expires in {days} days")
    if days < 3:
        await job_refresh_token()
    log_info("token", "", f"Token health check: {days} days remaining")


async def _send_token_warning(days: int) -> None:
    """Send the admin a token-expiry warning."""
    from app.services.telegram_bot import send_admin_alert

    await send_admin_alert(f"⚠️ Instagram token expires in {days} days.")


async def job_cleanup() -> None:
    """Clean up old log and processed media rows."""
    cleanup_old_data()
    log_info("scheduler", "", "Old log and processed rows deleted")


def start_scheduler() -> AsyncIOScheduler:
    """Start all recurring scheduler jobs and return the scheduler."""
    scheduler = AsyncIOScheduler()
    scheduler.add_job(job_refresh_followers, IntervalTrigger(minutes=60))
    scheduler.add_job(job_refresh_token, IntervalTrigger(days=45))
    scheduler.add_job(job_token_health_check, CronTrigger(hour=9, minute=0))
    scheduler.add_job(job_cleanup, CronTrigger(hour=0, minute=0))
    scheduler.start()
    return scheduler
