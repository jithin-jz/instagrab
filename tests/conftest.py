"""Shared pytest fixtures.

Important: this conftest sets environment variables BEFORE the application
package is imported anywhere else, so the cached :class:`Settings` instance
sees a deterministic test configuration and does not load the developer's
real ``.env`` file.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

import pytest

# Test environment must be set before any `app.*` import touches Settings.
_TEST_DB_DIR = Path(tempfile.mkdtemp(prefix="ig_tg_test_"))
os.environ.setdefault("DATABASE_PATH", str(_TEST_DB_DIR / "test.db"))
os.environ.setdefault("IG_APP_SECRET", "test-app-secret")
os.environ.setdefault("IG_VERIFY_TOKEN", "test-verify-token")
os.environ.setdefault("IG_ACCESS_TOKEN", "test-access-token")
os.environ.setdefault("IG_BUSINESS_ID", "1234567890")
os.environ.setdefault("TG_BOT_TOKEN", "1:test-bot-token")
os.environ.setdefault("TG_LOCAL_SERVER_URL", "https://api.telegram.org")
os.environ.setdefault("TG_WEBHOOK_SECRET", "test-tg-secret")
os.environ.setdefault("TG_POLLING", "1")
os.environ.setdefault("ADMIN_TELEGRAM_ID", "999")
os.environ.setdefault("BASE_URL", "https://example.test")
# Pydantic settings will still try to read .env. Ensure it does not exist
# inside the test runner's CWD by pointing the project model_config at a
# dummy file via env override is not possible — so callers should run pytest
# from a directory without a populated .env, or rely on env overrides above
# which take precedence over .env in pydantic-settings.

from app.settings import reset_settings_cache  # noqa: E402

reset_settings_cache()


@pytest.fixture
def fresh_db(monkeypatch: pytest.MonkeyPatch) -> Path:
    """Provide a per-test SQLite database file and re-initialize schema."""
    db_path = _TEST_DB_DIR / f"test-{uuid.uuid4().hex}.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    reset_settings_cache()
    from app.database import init_db

    init_db()
    yield db_path
    reset_settings_cache()


@pytest.fixture
def settings():
    """Return a fresh Settings instance for the current environment."""
    reset_settings_cache()
    from app.settings import get_settings

    return get_settings()
