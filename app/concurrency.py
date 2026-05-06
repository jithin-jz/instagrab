"""Process-wide async primitives shared across routers and services."""

from __future__ import annotations

import asyncio
from typing import Awaitable

from app.settings import get_settings

_background_tasks: set[asyncio.Task] = set()
_download_semaphore: asyncio.Semaphore | None = None


def get_download_semaphore() -> asyncio.Semaphore:
    """Lazily create a semaphore bound to the current running loop."""
    global _download_semaphore
    if _download_semaphore is None:
        limit = max(1, get_settings().MAX_CONCURRENT_DOWNLOADS)
        _download_semaphore = asyncio.Semaphore(limit)
    return _download_semaphore


def reset_download_semaphore() -> None:
    """Clear the cached semaphore (used by tests and shutdown)."""
    global _download_semaphore
    _download_semaphore = None


def spawn_background(coro: Awaitable[None]) -> asyncio.Task:
    """Spawn a tracked background task that survives the request lifetime."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


def get_background_tasks() -> set[asyncio.Task]:
    """Return the live set of tracked background tasks."""
    return _background_tasks


async def drain_background_tasks() -> None:
    """Await all tracked background tasks to completion."""
    if not _background_tasks:
        return
    await asyncio.gather(*list(_background_tasks), return_exceptions=True)
