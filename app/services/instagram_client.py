"""Instagram Graph API client functions."""

from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timezone

import httpx

from app.database import (
    get_config,
    is_follower_in_cache,
    replace_followers,
    set_config,
)
from app.logging import log_critical, log_error, log_info
from app.settings import get_settings

BASE_URL = "https://graph.instagram.com/v19.0"

_token_cache: str | None = None
_follower_sync_lock: asyncio.Lock | None = None
_last_follower_sync: float = 0.0


def _get_follower_sync_lock() -> asyncio.Lock:
    """Return a process-global asyncio lock for follower sync coalescing."""
    global _follower_sync_lock
    if _follower_sync_lock is None:
        _follower_sync_lock = asyncio.Lock()
    return _follower_sync_lock


def get_active_token() -> str:
    """Return the persisted access token, falling back to the configured one."""
    global _token_cache
    if _token_cache:
        return _token_cache
    token = get_config("access_token") or get_settings().IG_ACCESS_TOKEN
    _token_cache = token or None
    return token


def _set_token_cache(token: str) -> None:
    """Store a freshly issued token in the in-memory cache."""
    global _token_cache
    _token_cache = token or None


def _days_from_expiry(expires_at: str | None) -> int:
    """Convert an expiry timestamp string into remaining whole days."""
    if not expires_at:
        return 0
    try:
        remaining = float(expires_at) - time.time()
    except ValueError:
        return 0
    return max(0, int(remaining // 86400))


def _endpoint_url(path_or_url: str) -> str:
    """Build a full Graph API URL from a path or return an absolute URL."""
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        return path_or_url
    return f"{BASE_URL}/{path_or_url.lstrip('/')}"


async def refresh_access_token() -> bool:
    """Refresh the long-lived Instagram access token and persist it."""
    token = get_active_token()
    if not token:
        log_critical("token", "", "Token refresh failed: no active token configured")
        return False
    timeout = get_settings().HTTP_TIMEOUT_SECONDS
    params = {"grant_type": "ig_refresh_token", "access_token": token}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{BASE_URL}/refresh_access_token", params=params)
    except httpx.HTTPError as exc:
        log_critical("token", "", f"Token refresh request failed: {exc}")
        return False
    if response.status_code != 200:
        log_critical("token", "", f"Token refresh failed: {response.text[:300]}")
        return False
    return _persist_refreshed_token(response)


def _persist_refreshed_token(response: httpx.Response) -> bool:
    """Persist a successful token refresh response."""
    try:
        data = response.json()
        expires_in = int(data.get("expires_in", 0))
    except (TypeError, ValueError):
        log_critical("token", "", "Token refresh returned invalid JSON")
        return False
    new_token = data.get("access_token")
    if not new_token or expires_in <= 0:
        log_critical("token", "", "Token refresh response missing token or expiry")
        return False
    set_config("access_token", new_token)
    set_config("token_expires_at", str(time.time() + expires_in))
    os.environ["IG_ACCESS_TOKEN"] = new_token
    _set_token_cache(new_token)
    log_info("token", "", f"Token refreshed, expires in {expires_in // 86400} days")
    return True


def check_token_health() -> tuple[bool, int]:
    """Return whether the active token has remaining lifetime and its days left."""
    days = _days_from_expiry(get_config("token_expires_at"))
    return days > 0, days


async def _request_json(url: str, params: dict) -> tuple[int, dict, str]:
    """Issue an HTTP GET and return status code, parsed JSON, and raw text."""
    timeout = get_settings().HTTP_TIMEOUT_SECONDS
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(url, params=params)
    try:
        data = response.json()
    except ValueError:
        data = {}
    return response.status_code, data, response.text


async def _api_get(url: str, params: dict) -> dict:
    """Perform an authenticated Graph API GET with one token-refresh retry."""
    request_url = _endpoint_url(url)
    request_params = dict(params)
    request_params.setdefault("access_token", get_active_token())
    try:
        status, data, text = await _request_json(request_url, request_params)
        if status == 401 and await refresh_access_token():
            request_params["access_token"] = get_active_token()
            status, data, text = await _request_json(request_url, request_params)
    except httpx.HTTPError as exc:
        log_error("webhook", "", f"Instagram API request failed: {exc}")
        raise
    if status == 401:
        log_critical("token", "", f"Instagram API still unauthorized: {text[:300]}")
        raise RuntimeError("Instagram API authorization failed")
    if status >= 400:
        log_error("webhook", "", f"Instagram API error {status}: {text[:300]}")
        raise RuntimeError(f"Instagram API error {status}")
    return data


async def get_media_details(media_id: str) -> dict:
    """Fetch Instagram media details for a mentioned media ID."""
    fields = "id,media_type,media_url,video_url,caption,permalink,timestamp,owner"
    return await _api_get(f"/{media_id}", {"fields": fields})


async def get_user_info(ig_user_id: str) -> dict:
    """Fetch Instagram user profile details by user ID."""
    return await _api_get(f"/{ig_user_id}", {"fields": "id,username,name"})


def _next_after_cursor(response: dict) -> str | None:
    """Extract the next pagination cursor from a Graph API response."""
    paging = response.get("paging", {})
    cursors = paging.get("cursors", {})
    if paging.get("next") and cursors.get("after"):
        return str(cursors["after"])
    return None


async def fetch_all_followers() -> list[dict]:
    """Fetch every Instagram follower through cursor-based pagination."""
    business_id = get_settings().IG_BUSINESS_ID
    if not business_id:
        log_critical("follower_check", "", "IG_BUSINESS_ID is not configured")
        raise RuntimeError("IG_BUSINESS_ID is not configured")
    followers: list[dict] = []
    params: dict = {"fields": "id,username", "limit": 200}
    after: str | None = None
    while True:
        if after:
            params["after"] = after
        response = await _api_get(f"/{business_id}/followers", params)
        followers.extend(_clean_followers(response.get("data", [])))
        after = _next_after_cursor(response)
        if not after:
            break
    set_config("last_follower_sync", datetime.now(timezone.utc).isoformat())
    log_info("follower_check", "", f"Fetched {len(followers)} followers from Instagram")
    return followers


async def sync_followers(force: bool = False) -> bool:
    """Refresh the follower cache atomically with coalescing and TTL.

    Returns True if a sync ran, False if a recent sync was reused.
    Concurrent callers wait on a shared lock so we never trigger more than
    one full pagination at a time.
    """
    global _last_follower_sync
    ttl = get_settings().FOLLOWER_RESYNC_SECONDS
    if not force and time.time() - _last_follower_sync < ttl:
        return False
    lock = _get_follower_sync_lock()
    async with lock:
        if not force and time.time() - _last_follower_sync < ttl:
            return False
        followers = await fetch_all_followers()
        replace_followers(followers)
        _last_follower_sync = time.time()
    return True


def _clean_followers(items: list[dict]) -> list[dict]:
    """Filter follower payloads down to rows with ID and username."""
    return [
        {"id": str(item["id"]), "username": str(item["username"]).lower()}
        for item in items
        if item.get("id") and item.get("username")
    ]


async def check_is_follower(ig_user_id: str) -> bool:
    """Confirm whether an Instagram user follows the target account."""
    if is_follower_in_cache(ig_user_id):
        return True
    await sync_followers(force=False)
    return is_follower_in_cache(ig_user_id)
