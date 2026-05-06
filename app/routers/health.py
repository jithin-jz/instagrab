"""Service health and statistics endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from app.database import get_stats_summary
from app.services.instagram_client import check_token_health

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Return current service health and delivery statistics."""
    is_valid, days = check_token_health()
    stats = get_stats_summary()
    return {
        "status": "running",
        "token_valid": is_valid,
        "token_days_remaining": days,
        "total_users": stats["total_users"],
        "total_delivered": stats["total_delivered"],
        "followers_cached": stats["followers_cached"],
        "last_follower_sync": stats["last_follower_sync"],
    }
