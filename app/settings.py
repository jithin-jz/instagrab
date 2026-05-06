"""Typed application settings loaded from environment variables and .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the Instagram to Telegram delivery bot."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    IG_APP_ID: str = ""
    IG_APP_SECRET: str = ""
    IG_VERIFY_TOKEN: str = ""
    IG_ACCESS_TOKEN: str = ""
    IG_BUSINESS_ID: str = ""

    TG_BOT_TOKEN: str = ""
    TG_LOCAL_SERVER_URL: str = "https://api.telegram.org"
    TG_WEBHOOK_SECRET: str = ""
    TG_POLLING: bool = False
    ADMIN_TELEGRAM_ID: str = ""

    BASE_URL: str = ""
    DATABASE_PATH: Path = Field(default=Path("instagrab.db"))
    DATABASE_URL: str = Field(default="postgresql://user:password@localhost:5432/instagrab")

    MAX_CONCURRENT_DOWNLOADS: int = 3
    RATE_LIMIT_SECONDS: int = 60
    MAX_WEBHOOK_BODY_BYTES: int = 2 * 1024 * 1024
    FOLLOWER_RESYNC_SECONDS: int = 30 * 60
    HTTP_TIMEOUT_SECONDS: float = 30.0

    @property
    def telegram_local_server_url(self) -> str:
        """Telegram Bot API base URL with trailing slash trimmed."""
        return self.TG_LOCAL_SERVER_URL.rstrip("/")

    @property
    def use_local_telegram_server(self) -> bool:
        """Whether the bot is pointed at a self-hosted Bot API server."""
        return self.telegram_local_server_url != "https://api.telegram.org"

    @property
    def telegram_base_url(self) -> str:
        """Base URL for Telegram bot API requests."""
        return f"{self.telegram_local_server_url}/bot"

    @property
    def telegram_file_base_url(self) -> str:
        """Base URL for Telegram file downloads."""
        return f"{self.telegram_local_server_url}/file/bot"

    @property
    def admin_chat_id(self) -> str | None:
        """Normalized admin chat identifier or ``None`` if unset."""
        value = (self.ADMIN_TELEGRAM_ID or "").strip()
        return value or None

    @property
    def max_telegram_file_mb(self) -> int:
        """Per-message file size limit in megabytes for the active backend."""
        return 2000 if self.use_local_telegram_server else 50

    @property
    def telegram_webhook_url(self) -> str | None:
        """Public URL Telegram should call when delivering updates."""
        if not self.BASE_URL:
            return None
        base = self.BASE_URL.rstrip("/")
        return f"{base}/telegram/webhook"

    @property
    def use_telegram_webhook(self) -> bool:
        """Whether to register a webhook instead of long polling."""
        if self.TG_POLLING:
            return False
        return bool(self.TG_WEBHOOK_SECRET and self.telegram_webhook_url)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance for the running process."""
    return Settings()


def reset_settings_cache() -> None:
    """Clear the cached settings instance (used by tests)."""
    get_settings.cache_clear()
