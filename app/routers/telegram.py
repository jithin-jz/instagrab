"""Telegram webhook endpoint that pushes updates into the bot's queue."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from telegram import Update

from app.services.telegram_bot import get_application
from app.settings import get_settings

router = APIRouter(tags=["telegram"])

_SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"


@router.post("/telegram/webhook")
async def telegram_webhook(request: Request) -> JSONResponse:
    """Accept Telegram bot updates pushed by the Bot API webhook."""
    settings = get_settings()
    secret = settings.TG_WEBHOOK_SECRET
    if not secret:
        raise HTTPException(status_code=404, detail="Telegram webhook disabled")
    if request.headers.get(_SECRET_HEADER, "") != secret:
        raise HTTPException(status_code=403, detail="Invalid webhook secret")
    application = get_application()
    if application is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")
    raw = await request.json()
    update = Update.de_json(raw, application.bot)
    await application.update_queue.put(update)
    return JSONResponse({"status": "ok"})
