"""Pydantic models for Instagram webhook payloads."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class MentionValue(BaseModel):
    """Inner ``value`` block of a mention webhook change."""

    model_config = ConfigDict(extra="ignore")
    media_id: str | None = None
    comment_id: str | None = None


class WebhookChange(BaseModel):
    """One change record inside an Instagram webhook entry."""

    model_config = ConfigDict(extra="ignore")
    field: str = ""
    value: MentionValue = Field(default_factory=MentionValue)


class WebhookEntry(BaseModel):
    """One entry in the top-level webhook payload."""

    model_config = ConfigDict(extra="ignore")
    id: str | None = None
    time: int | None = None
    changes: list[WebhookChange] = Field(default_factory=list)


class InstagramWebhookPayload(BaseModel):
    """Top-level Instagram webhook payload."""

    model_config = ConfigDict(extra="ignore")
    object: str | None = None
    entry: list[WebhookEntry] = Field(default_factory=list)
