"""Telegram bot registration flow, admin commands, and media delivery."""

from __future__ import annotations

import asyncio
import html
import re
from typing import BinaryIO

from telegram import Update
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.database import (
    delete_user,
    get_pending_unregistered,
    get_recent_logs,
    get_recent_users,
    get_stats_summary,
    get_user_by_chat_id,
    save_user,
)
from app.logging import log_error, log_warning
from app.services.instagram_client import check_token_health
from app.settings import get_settings

WAITING_FOR_USERNAME = 1
USERNAME_PATTERN = re.compile(r"^[a-z0-9._]{1,30}$")
CAPTION_LIMIT = 800

_app: Application | None = None


def set_application(application: Application | None) -> None:
    """Register the active Telegram application for cross-module sends."""
    global _app
    _app = application


def get_application() -> Application | None:
    """Return the active Telegram application if any."""
    return _app


def _get_bot():
    """Return the active Telegram bot instance, or None if not initialized."""
    return _app.bot if _app is not None else None


def _normalize_username(value: str) -> str:
    """Normalize a user-submitted Instagram username."""
    return value.strip().lstrip("@").lower()


def is_valid_username(value: str) -> bool:
    """Return whether a username matches Instagram's basic username rules."""
    return bool(USERNAME_PATTERN.fullmatch(value)) and " " not in value


def _chat_id(update: Update) -> str:
    """Return the effective Telegram chat ID as a string."""
    if update.effective_chat is None:
        return ""
    return str(update.effective_chat.id)


def _is_admin(update: Update) -> bool:
    """Return whether the update came from the configured admin chat."""
    admin = get_settings().admin_chat_id
    return bool(admin and _chat_id(update) == admin)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the Instagram username registration conversation."""
    del context
    if update.message:
        await update.message.reply_text(
            "👋 Welcome! To receive downloads, I need your Instagram username.\n"
            "Send it now (without the @ symbol):"
        )
    return WAITING_FOR_USERNAME


async def receive_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Validate and save the Instagram username sent during registration."""
    del context
    if not update.message or not update.effective_chat:
        return WAITING_FOR_USERNAME
    username = _normalize_username(update.message.text or "")
    if not is_valid_username(username):
        await update.message.reply_text(
            "❌ Invalid username. Use 1-30 letters, numbers, dots, or underscores only."
        )
        return WAITING_FOR_USERNAME
    save_user(username, str(update.effective_chat.id))
    pending_note = _pending_registration_note(username)
    await update.message.reply_text(
        "✅ Linked successfully!\n"
        f"Instagram: @{username}\n"
        "Now tag @TargetAccount in any Instagram post comment.\n"
        f"Your download will arrive here within seconds! 🚀{pending_note}"
    )
    return ConversationHandler.END


def _pending_registration_note(username: str) -> str:
    """Return an extra confirmation note if prior unregistered tags exist."""
    if not get_pending_unregistered(username):
        return ""
    return "\nWe noticed you already tagged us — tag again and we'll deliver it!"


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send usage instructions for the Telegram bot."""
    del context
    if update.message:
        await update.message.reply_text(
            "📖 How to use:\n"
            "1. Make sure you follow @TargetAccount on Instagram\n"
            "2. Find any reel or post you want to download\n"
            "3. Comment @TargetAccount on it\n"
            "4. Your download appears here in seconds!\n\n"
            "Commands:\n"
            "/me — see your account info\n"
            "/unlink — remove your account\n"
            "/help — show this message"
        )


async def me_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the current user's linked Instagram account and delivery stats."""
    del context
    user = get_user_by_chat_id(_chat_id(update))
    if not update.message:
        return
    if not user:
        await update.message.reply_text("You haven't registered yet. Send /start to begin.")
        return
    await update.message.reply_text(_format_me(user))


def _format_me(user: dict) -> str:
    """Format the /me response for a registered user."""
    last_delivery = user.get("last_delivery_at") or "Never"
    return (
        "👤 Your account:\n"
        f"Instagram: @{user['ig_username']}\n"
        f"Registered: {user['registered_at']}\n"
        f"Total downloads received: {user['total_delivered']}\n"
        f"Last delivery: {last_delivery}"
    )


async def unlink_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove the current Telegram chat's linked Instagram account."""
    del context
    user = get_user_by_chat_id(_chat_id(update))
    if not update.message:
        return
    if not user:
        await update.message.reply_text("You haven't registered yet. Send /start to begin.")
        return
    delete_user(user["ig_username"])
    await update.message.reply_text(f"✅ Unlinked @{user['ig_username']} successfully.")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send aggregate system statistics to the admin user."""
    del context
    if not _is_admin(update) or not update.message:
        return
    stats = get_stats_summary()
    _, days = check_token_health()
    await update.message.reply_text(_format_stats(stats, days))


def _format_stats(stats: dict, token_days: int) -> str:
    """Format system counters for the /stats admin command."""
    return (
        "📊 System Stats:\n"
        f"👥 Registered users: {stats['total_users']}\n"
        f"📦 Total deliveries: {stats['total_delivered']}\n"
        f"❌ Failed deliveries: {stats['total_failed']}\n"
        f"👥 Followers cached: {stats['followers_cached']}\n"
        f"🔑 Token expires in: {token_days} days\n"
        f"🕐 Last follower sync: {stats['last_follower_sync'] or 'Never'}"
    )


async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the most recent log entries to the admin user."""
    del context
    if not _is_admin(update) or not update.message:
        return
    logs = get_recent_logs(10)
    text = "\n".join(_format_log_line(row) for row in logs) or "No logs yet."
    await update.message.reply_text(text)


def _format_log_line(row: dict) -> str:
    """Format one database log row for Telegram output."""
    username = f"@{row['ig_username']}" if row.get("ig_username") else "-"
    return f"{row['created_at']} | {row['level']} | {row['event_type']} | {username} | {row['detail']}"


async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the most recently registered users to the admin user."""
    del context
    if not _is_admin(update) or not update.message:
        return
    users = get_recent_users(10)
    text = "\n".join(_format_user_line(row) for row in users) or "No users registered."
    await update.message.reply_text(text)


def _format_user_line(row: dict) -> str:
    """Format one registered user row for Telegram output."""
    return (
        f"@{row['ig_username']} | chat {row['telegram_chat_id']} | "
        f"{row['total_delivered']} delivered | {row['registered_at']}"
    )


def truncate_caption(caption: str) -> str:
    """Trim the Instagram caption to fit under Telegram caption limits."""
    return caption[:CAPTION_LIMIT] if caption else ""


def build_caption(caption: str, permalink: str) -> str:
    """Build an HTML-formatted Telegram caption with safe escaping."""
    body = html.escape(truncate_caption(caption))
    safe_link = html.escape(permalink, quote=True)
    return f"{body}\n\n\U0001f517 <a href=\"{safe_link}\">View Original</a>"


async def _open_binary(file_path: str) -> BinaryIO:
    """Open a binary file without blocking the event loop."""
    return await asyncio.to_thread(open, file_path, "rb")


async def send_media_to_user(
    chat_id: str,
    file_path: str,
    kind: str,
    caption: str,
    permalink: str,
    size_mb: float,
) -> bool:
    """Send a downloaded media file privately to a Telegram chat."""
    bot = _get_bot()
    if bot is None:
        log_error("delivery", "", "Telegram application not initialized")
        return False
    max_mb = get_settings().max_telegram_file_mb
    if size_mb > max_mb:
        await send_user_message(
            chat_id,
            f"\u26a0\ufe0f This file is {size_mb:.1f}MB which exceeds the {max_mb}MB "
            "limit. Try a shorter reel.",
        )
        log_warning("delivery", "", f"File for chat {chat_id} exceeded size limit")
        return False
    full_caption = build_caption(caption, permalink)
    file_obj = await _open_binary(file_path)
    try:
        await _send_open_file(bot, chat_id, file_obj, kind, full_caption)
    except TelegramError as exc:
        log_error("delivery", "", f"Telegram send failed for chat {chat_id}: {exc}")
        return False
    finally:
        await asyncio.to_thread(file_obj.close)
    return True


async def _send_open_file(
    bot,
    chat_id: str,
    file_obj: BinaryIO,
    kind: str,
    full_caption: str,
) -> None:
    """Send an already opened file through the correct Telegram method."""
    if kind == "video":
        await bot.send_video(
            chat_id=chat_id,
            video=file_obj,
            caption=full_caption,
            parse_mode=ParseMode.HTML,
            supports_streaming=True,
        )
        return
    await bot.send_photo(
        chat_id=chat_id,
        photo=file_obj,
        caption=full_caption,
        parse_mode=ParseMode.HTML,
    )


async def send_admin_alert(message: str) -> None:
    """Send an alert message to the configured admin chat if possible."""
    bot = _get_bot()
    admin = get_settings().admin_chat_id
    if not admin or bot is None:
        return
    try:
        await bot.send_message(chat_id=admin, text=message)
    except TelegramError:
        return


async def send_user_message(chat_id: str, message: str) -> None:
    """Send a plain text Telegram message to a user if possible."""
    bot = _get_bot()
    if bot is None:
        return
    try:
        await bot.send_message(chat_id=chat_id, text=message)
    except TelegramError:
        return


def build_bot_app() -> Application:
    """Build the Telegram application and register all command handlers."""
    settings = get_settings()
    if not settings.TG_BOT_TOKEN:
        raise RuntimeError("TG_BOT_TOKEN is required")
    builder = (
        ApplicationBuilder()
        .token(settings.TG_BOT_TOKEN)
        .base_url(settings.telegram_base_url)
        .base_file_url(settings.telegram_file_base_url)
        .local_mode(settings.use_local_telegram_server)
    )
    if settings.use_telegram_webhook:
        builder = builder.updater(None)
    app = builder.build()
    app.add_handler(_registration_handler())
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("me", me_command))
    app.add_handler(CommandHandler("unlink", unlink_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("logs", logs_command))
    app.add_handler(CommandHandler("users", users_command))
    return app


def _registration_handler() -> ConversationHandler:
    """Create the /start registration conversation handler."""
    return ConversationHandler(
        entry_points=[CommandHandler("start", start_command)],
        states={
            WAITING_FOR_USERNAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_username)
            ]
        },
        fallbacks=[],
        allow_reentry=True,
    )
