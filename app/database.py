"""SQLite persistence for the Instagram to Telegram delivery system."""

from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from app.settings import get_settings

FRESH_FOLLOWER_SECONDS = 2 * 60 * 60


def _db_path() -> Path:
    """Return the configured SQLite database path."""
    return Path(get_settings().DATABASE_PATH).expanduser()


@contextmanager
def _connection() -> Iterator[sqlite3.Connection]:
    """Open a short-lived SQLite connection and close it safely."""
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _normalize_username(ig_username: str) -> str:
    """Normalize an Instagram username for consistent lookups."""
    return ig_username.strip().lstrip("@").lower()


def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    """Convert a SQLite row to a regular dictionary."""
    return dict(row) if row is not None else None


def _timestamp_to_unix(value: str | None) -> float | None:
    """Convert a SQLite timestamp string to a Unix timestamp."""
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(value.split(".")[0], fmt)
            return dt.replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
    return None


def init_db() -> None:
    """Create all required database tables and indexes if missing."""
    with _connection() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        _create_user_tables(conn)
        _create_event_tables(conn)
        _create_config_table(conn)


def _create_user_tables(conn: sqlite3.Connection) -> None:
    """Create user and follower tables."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ig_username TEXT UNIQUE NOT NULL,
            telegram_chat_id TEXT NOT NULL,
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_delivery_at TIMESTAMP,
            total_delivered INTEGER DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS followers (
            ig_user_id TEXT PRIMARY KEY,
            ig_username TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _create_event_tables(conn: sqlite3.Connection) -> None:
    """Create processed media and log tables."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS processed (
            media_id TEXT PRIMARY KEY,
            ig_username TEXT,
            status TEXT,
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            level TEXT,
            event_type TEXT,
            ig_username TEXT,
            detail TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _create_config_table(conn: sqlite3.Connection) -> None:
    """Create the persistent key-value configuration table."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def save_user(ig_username: str, telegram_chat_id: str) -> None:
    """Register or replace a Telegram chat for an Instagram username."""
    username = _normalize_username(ig_username)
    with _connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO users (ig_username, telegram_chat_id)
            VALUES (?, ?)
            """,
            (username, telegram_chat_id),
        )


def get_telegram_id(ig_username: str) -> str | None:
    """Return the Telegram chat ID linked to an Instagram username."""
    username = _normalize_username(ig_username)
    with _connection() as conn:
        row = conn.execute(
            "SELECT telegram_chat_id FROM users WHERE ig_username = ?",
            (username,),
        ).fetchone()
    return str(row["telegram_chat_id"]) if row else None


def get_user_stats(ig_username: str) -> dict | None:
    """Return the complete user row for an Instagram username."""
    username = _normalize_username(ig_username)
    with _connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE ig_username = ?",
            (username,),
        ).fetchone()
    return _row_to_dict(row)


def get_user_by_chat_id(telegram_chat_id: str) -> dict | None:
    """Return the registered user row for a Telegram chat ID."""
    with _connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE telegram_chat_id = ?",
            (telegram_chat_id,),
        ).fetchone()
    return _row_to_dict(row)


def delete_user(ig_username: str) -> None:
    """Delete a user registration by Instagram username."""
    username = _normalize_username(ig_username)
    with _connection() as conn:
        conn.execute("DELETE FROM users WHERE ig_username = ?", (username,))


def replace_followers(followers: list[dict]) -> None:
    """Atomically replace the entire follower cache with the given list."""
    rows = [
        (str(item["id"]), _normalize_username(str(item.get("username", ""))))
        for item in followers
        if item.get("id") and item.get("username")
    ]
    with _connection() as conn:
        conn.execute("DELETE FROM followers")
        if rows:
            conn.executemany(
                """
                INSERT INTO followers (ig_user_id, ig_username, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                """,
                rows,
            )


def is_follower_in_cache(ig_user_id: str) -> bool:
    """Return whether a follower row exists in the cache, regardless of age."""
    with _connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM followers WHERE ig_user_id = ?",
            (ig_user_id,),
        ).fetchone()
    return row is not None


def get_followers_count() -> int:
    """Return the number of followers currently cached."""
    with _connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS total FROM followers").fetchone()
    return int(row["total"])


def get_last_sync_time() -> str | None:
    """Return the persisted timestamp of the most recent follower sync."""
    return get_config("last_follower_sync")


def set_config(key: str, value: str) -> None:
    """Persist a configuration value by key."""
    with _connection() as conn:
        conn.execute(
            """
            INSERT INTO config (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (key, value),
        )


def get_config(key: str) -> str | None:
    """Return a persisted configuration value by key."""
    with _connection() as conn:
        row = conn.execute(
            "SELECT value FROM config WHERE key = ?",
            (key,),
        ).fetchone()
    return str(row["value"]) if row and row["value"] is not None else None


def is_already_processed(media_id: str) -> bool:
    """Return whether a media ID already has a processed record."""
    with _connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM processed WHERE media_id = ?",
            (media_id,),
        ).fetchone()
    return row is not None


def mark_processed(media_id: str, ig_username: str, status: str) -> None:
    """Insert a processed media record if one does not already exist."""
    username = _normalize_username(ig_username)
    with _connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO processed (media_id, ig_username, status)
            VALUES (?, ?, ?)
            """,
            (media_id, username, status),
        )


def get_pending_unregistered(ig_username: str) -> bool:
    """Return whether a user previously tagged before registering."""
    username = _normalize_username(ig_username)
    with _connection() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM processed
            WHERE ig_username = ? AND status = 'not_registered'
            LIMIT 1
            """,
            (username,),
        ).fetchone()
    return row is not None


def get_last_delivery_time(telegram_chat_id: str) -> float | None:
    """Return the Unix timestamp of a chat's most recent delivery."""
    with _connection() as conn:
        row = conn.execute(
            """
            SELECT last_delivery_at
            FROM users
            WHERE telegram_chat_id = ?
            """,
            (telegram_chat_id,),
        ).fetchone()
    return _timestamp_to_unix(row["last_delivery_at"]) if row else None


def try_reserve_delivery(
    telegram_chat_id: str, window_seconds: int
) -> tuple[bool, int]:
    """Atomically reserve a delivery slot for a chat.

    Returns ``(allowed, remaining_seconds)``. When allowed, the user's
    ``last_delivery_at`` is moved forward to ``CURRENT_TIMESTAMP`` so
    concurrent attempts inside the same rate-limit window are rejected.
    """
    cutoff = f"-{int(window_seconds)} seconds"
    with _connection() as conn:
        cursor = conn.execute(
            """
            UPDATE users
            SET last_delivery_at = CURRENT_TIMESTAMP
            WHERE telegram_chat_id = ?
              AND (last_delivery_at IS NULL
                   OR last_delivery_at <= datetime('now', ?))
            """,
            (telegram_chat_id, cutoff),
        )
        if cursor.rowcount > 0:
            return True, 0
        row = conn.execute(
            "SELECT last_delivery_at FROM users WHERE telegram_chat_id = ?",
            (telegram_chat_id,),
        ).fetchone()
    if row is None:
        return True, 0
    last_unix = _timestamp_to_unix(row["last_delivery_at"])
    if last_unix is None:
        return True, 0
    elapsed = time.time() - last_unix
    remaining = max(1, int(window_seconds - elapsed))
    return False, remaining


def update_delivery_stats(ig_username: str) -> None:
    """Update a user's last delivery time and total delivery count."""
    username = _normalize_username(ig_username)
    with _connection() as conn:
        conn.execute(
            """
            UPDATE users
            SET last_delivery_at = CURRENT_TIMESTAMP,
                total_delivered = total_delivered + 1
            WHERE ig_username = ?
            """,
            (username,),
        )


def get_stats_summary() -> dict:
    """Return aggregate system counters for admin and health views."""
    with _connection() as conn:
        users = conn.execute("SELECT COUNT(*) AS total FROM users").fetchone()
        delivered = conn.execute(
            "SELECT COALESCE(SUM(total_delivered), 0) AS total FROM users"
        ).fetchone()
        failed = conn.execute(
            "SELECT COUNT(*) AS total FROM processed WHERE status = 'failed'"
        ).fetchone()
        followers = conn.execute("SELECT COUNT(*) AS total FROM followers").fetchone()
    return {
        "total_users": int(users["total"]),
        "total_delivered": int(delivered["total"]),
        "total_failed": int(failed["total"]),
        "followers_cached": int(followers["total"]),
        "last_follower_sync": get_last_sync_time(),
    }


def insert_log(level: str, event_type: str, ig_username: str, detail: str) -> None:
    """Insert a structured log row into the database."""
    username = _normalize_username(ig_username) if ig_username else ""
    with _connection() as conn:
        conn.execute(
            """
            INSERT INTO logs (level, event_type, ig_username, detail)
            VALUES (?, ?, ?, ?)
            """,
            (level, event_type, username, detail),
        )


def get_recent_logs(limit: int = 10) -> list[dict]:
    """Return the most recent log rows in reverse chronological order."""
    with _connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM logs
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_recent_users(limit: int = 10) -> list[dict]:
    """Return the most recently registered users."""
    with _connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM users
            ORDER BY registered_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def cleanup_old_data() -> None:
    """Delete old logs and processed media records."""
    with _connection() as conn:
        conn.execute("DELETE FROM logs WHERE created_at < datetime('now', '-30 days')")
        conn.execute(
            "DELETE FROM processed WHERE processed_at < datetime('now', '-7 days')"
        )
