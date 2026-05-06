"""Instagram webhook endpoints."""

from __future__ import annotations

import hashlib
import hmac
import json
from json import JSONDecodeError

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.concurrency import spawn_background
from app.logging import log_info, log_warning
from app.schemas import InstagramWebhookPayload
from app.services.delivery import handle_payload
from app.settings import get_settings

router = APIRouter(tags=["instagram"])


def _verify_signature(body: bytes, signature: str) -> bool:
    """Validate the Instagram X-Hub-Signature-256 header."""
    app_secret = get_settings().IG_APP_SECRET
    if not app_secret or not signature.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


def _payload_log_detail(payload: dict) -> str:
    """Serialize a webhook payload for compact database logging."""
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)[:4000]


@router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query("", alias="hub.mode"),
    hub_verify_token: str = Query("", alias="hub.verify_token"),
    hub_challenge: str = Query("", alias="hub.challenge"),
) -> int:
    """Verify the Instagram webhook subscription handshake."""
    expected_token = get_settings().IG_VERIFY_TOKEN
    if hub_mode == "subscribe" and hub_verify_token == expected_token:
        try:
            return int(hub_challenge)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid challenge") from exc
    raise HTTPException(status_code=403, detail="Webhook verification failed")


@router.post("/webhook")
async def instagram_webhook(request: Request) -> JSONResponse:
    """Accept Instagram mention webhooks and process them in the background."""
    settings = get_settings()
    max_bytes = settings.MAX_WEBHOOK_BODY_BYTES
    content_length = request.headers.get("content-length", "")
    if content_length.isdigit() and int(content_length) > max_bytes:
        raise HTTPException(status_code=413, detail="Payload too large")
    body = await request.body()
    if len(body) > max_bytes:
        raise HTTPException(status_code=413, detail="Payload too large")
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not _verify_signature(body, signature):
        client_host = request.client.host if request.client else "unknown"
        log_warning(
            "webhook",
            "",
            f"Invalid webhook signature rejected from {client_host}",
        )
        raise HTTPException(status_code=401, detail="Invalid signature")
    try:
        raw = json.loads(body)
    except JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc
    try:
        payload = InstagramWebhookPayload.model_validate(raw)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="Invalid payload schema") from exc
    log_info("webhook", "", _payload_log_detail(raw))
    spawn_background(handle_payload(payload))
    return JSONResponse({"status": "ok"})
