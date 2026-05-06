"""Structured console and database logging."""

from __future__ import annotations

import asyncio
from datetime import datetime

from app.database import insert_log

EMOJI_MAP = {
    "INFO": "✅",
    "WARNING": "⚠️",
    "ERROR": "❌",
    "CRITICAL": "🚨",
}


def _format_username(ig_username: str | None) -> str:
    """Format an Instagram username for log output."""
    if not ig_username:
        return "-"
    return f"@{ig_username.strip().lstrip('@').lower()}"


def _send_critical_alert(detail: str) -> None:
    """Schedule an admin alert for critical log entries when a loop is running."""
    try:
        from app.services.telegram_bot import send_admin_alert
    except (ImportError, RuntimeError):
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(send_admin_alert(detail))


def log(level: str, event_type: str, ig_username: str, detail: str) -> None:
    """Print a structured log line and persist it to the database."""
    normalized_level = level.upper()
    emoji = EMOJI_MAP.get(normalized_level, "•")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    username = _format_username(ig_username)
    line = f"{timestamp} | {emoji} {normalized_level} | {event_type} | {username} | {detail}"
    print(line, flush=True)
    insert_log(normalized_level, event_type, ig_username, detail)
    if normalized_level == "CRITICAL":
        _send_critical_alert(detail)


def log_info(event_type: str, ig_username: str, detail: str) -> None:
    """Write an INFO level structured log entry."""
    log("INFO", event_type, ig_username, detail)


def log_warning(event_type: str, ig_username: str, detail: str) -> None:
    """Write a WARNING level structured log entry."""
    log("WARNING", event_type, ig_username, detail)


def log_error(event_type: str, ig_username: str, detail: str) -> None:
    """Write an ERROR level structured log entry."""
    log("ERROR", event_type, ig_username, detail)


def log_critical(event_type: str, ig_username: str, detail: str) -> None:
    """Write a CRITICAL level structured log entry."""
    log("CRITICAL", event_type, ig_username, detail)
