"""End-to-end delivery pipeline for mentioned Instagram media."""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile

from app.concurrency import get_download_semaphore
from app.database import (
    get_telegram_id,
    is_already_processed,
    mark_processed,
    try_reserve_delivery,
    update_delivery_stats,
)
from app.logging import log_error, log_info, log_warning
from app.schemas import InstagramWebhookPayload
from app.services.downloader import TEMP_PREFIX, download_media
from app.services.instagram_client import (
    check_is_follower,
    get_media_details,
    get_user_info,
)
from app.services.telegram_bot import (
    send_admin_alert,
    send_media_to_user,
    send_user_message,
)
from app.settings import get_settings


async def handle_payload(payload: InstagramWebhookPayload) -> None:
    """Process mention changes from a parsed Instagram webhook payload."""
    for entry in payload.entry:
        for change in entry.changes:
            if change.field != "mentions":
                continue
            media_id = change.value.media_id
            if media_id:
                await process_mention(str(media_id))


async def process_mention(media_id: str) -> None:
    """Process one mentioned Instagram media item through delivery."""
    file_path: str | None = None
    semaphore = get_download_semaphore()
    async with semaphore:
        try:
            if is_already_processed(media_id):
                log_info("webhook", "", f"Duplicate skipped: {media_id}")
                return
            media = await get_media_details(media_id)
            media_context = _extract_media_context(media)
            ig_user_id = media_context["ig_user_id"]
            if not ig_user_id:
                log_warning("webhook", "", "No owner ID in media — skipping")
                return
            user_info = await get_user_info(ig_user_id)
            ig_username = str(user_info.get("username", "")).lower()
            file_path = await _deliver_media(
                media_id, ig_user_id, ig_username, media_context
            )
        except Exception as exc:  # noqa: BLE001 — top-level worker boundary
            log_error("delivery", "", f"Processing failed for {media_id}: {exc}")
        finally:
            _cleanup_download(file_path)


def _extract_media_context(media: dict) -> dict:
    """Extract the media fields needed by the delivery pipeline."""
    owner = media.get("owner") or {}
    return {
        "permalink": media.get("permalink", ""),
        "caption": media.get("caption", ""),
        "media_type": media.get("media_type", "IMAGE"),
        "direct_url": media.get("video_url") or media.get("media_url"),
        "ig_user_id": str(owner.get("id", "")),
    }


async def _deliver_media(
    media_id: str,
    ig_user_id: str,
    ig_username: str,
    media_context: dict,
) -> str | None:
    """Run follower, registration, rate-limit, download, and send steps."""
    log_info("webhook", ig_username, f"Tagged media: {media_id}")
    if not await _confirm_follower(media_id, ig_user_id, ig_username):
        return None
    telegram_chat_id = await _lookup_telegram_chat(media_id, ig_username)
    if not telegram_chat_id or not await _allow_delivery(telegram_chat_id):
        return None
    file_path, kind, size_mb = await asyncio.to_thread(
        download_media,
        media_context["permalink"],
        media_context["direct_url"],
        media_context["media_type"],
    )
    log_info("download", ig_username, f"{kind} downloaded {size_mb:.1f}MB")
    await _finalize_delivery(
        media_id, ig_username, telegram_chat_id, media_context, file_path, kind, size_mb
    )
    return file_path


async def _confirm_follower(media_id: str, ig_user_id: str, ig_username: str) -> bool:
    """Check follower status and mark ignored media when needed."""
    is_follower = await check_is_follower(ig_user_id)
    if not is_follower:
        mark_processed(media_id, ig_username, "not_follower")
        log_info("follower_check", ig_username, "Not a follower — ignored")
        return False
    log_info("follower_check", ig_username, "Follower confirmed")
    return True


async def _lookup_telegram_chat(media_id: str, ig_username: str) -> str | None:
    """Find the Telegram chat ID for a registered Instagram username."""
    telegram_chat_id = get_telegram_id(ig_username)
    if telegram_chat_id:
        return telegram_chat_id
    mark_processed(media_id, ig_username, "not_registered")
    log_warning("delivery", ig_username, "Not registered on Telegram")
    await send_admin_alert(
        f"⚠️ @{ig_username} tagged you (follower) but has no Telegram registered."
    )
    return None


async def _allow_delivery(telegram_chat_id: str) -> bool:
    """Atomically reserve a per-user delivery slot under the rate limit."""
    window = get_settings().RATE_LIMIT_SECONDS
    allowed, remaining = try_reserve_delivery(telegram_chat_id, window)
    if allowed:
        return True
    await send_user_message(
        telegram_chat_id,
        f"⏳ Please wait {remaining}s before requesting another download.",
    )
    return False


async def _finalize_delivery(
    media_id: str,
    ig_username: str,
    telegram_chat_id: str,
    media_context: dict,
    file_path: str,
    kind: str,
    size_mb: float,
) -> None:
    """Send the downloaded file and record the final delivery outcome."""
    success = await send_media_to_user(
        telegram_chat_id,
        file_path,
        kind,
        media_context["caption"],
        media_context["permalink"],
        size_mb,
    )
    if success:
        mark_processed(media_id, ig_username, "delivered")
        update_delivery_stats(ig_username)
        log_info("delivery", ig_username, f"{kind} {size_mb:.1f}MB delivered ✅")
        return
    mark_processed(media_id, ig_username, "failed")
    log_error("delivery", ig_username, "Send failed")


def _cleanup_download(file_path: str | None) -> None:
    """Remove a downloaded temp file and its temporary directory."""
    if not file_path:
        return
    parent = os.path.abspath(os.path.dirname(file_path))
    temp_root = os.path.abspath(tempfile.gettempdir())
    try:
        inside_temp = os.path.commonpath([parent, temp_root]) == temp_root
    except ValueError:
        inside_temp = False
    if os.path.basename(parent).startswith(TEMP_PREFIX) and inside_temp:
        shutil.rmtree(parent, ignore_errors=True)
    elif os.path.exists(file_path):
        os.remove(file_path)
