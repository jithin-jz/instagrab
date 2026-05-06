"""PostgreSQL persistence for the Instagram to Telegram delivery system."""

from __future__ import annotations

import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

from app.settings import get_settings

FRESH_FOLLOWER_SECONDS = 2 * 60 * 60

_connection_pool: pool.SimpleConnectionPool | None = None


def _get_pool() -> pool.SimpleConnectionPool:
    """Get or create the PostgreSQL connection pool."""
    global _connection_pool
    if _connection_pool is None:
        settings = get_settings()
        _connection_pool = pool.SimpleConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=settings.DATABASE_URL,
        )
    return _connection_pool


@contextmanager
def _connection():
    """Open a short-lived PostgreSQL connection and close it safely."""
    pool = _get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            yield cursor
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def _normalize_username(ig_username: str) -> str:
    """Normalize an Instagram username for consistent lookups."""
    return ig_username.strip().lstrip("@").lower()


def _row_to_dict(row) -> dict | None:
    """Convert a PostgreSQL row to a regular dictionary."""
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
    with _connection() as cursor:
        _create_user_tables(cursor)
        _create_event_tables(cursor)
        _create_config_table(cursor)


def _create_user_tables(cursor) -> None:
    """Create user and follower tables."""
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            ig_username TEXT UNIQUE NOT NULL,
            telegram_chat_id TEXT NOT NULL,
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_delivery_at TIMESTAMP,
            total_delivered INTEGER DEFAULT 0
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS followers (
            ig_user_id TEXT PRIMARY KEY,
            ig_username TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _create_event_tables(cursor) -> None:
    """Create processed media and log tables."""
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS processed (
            media_id TEXT PRIMARY KEY,
            ig_username TEXT,
            status TEXT,
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS logs (
            id SERIAL PRIMARY KEY,
            level TEXT,
            event_type TEXT,
            ig_username TEXT,
            detail TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _create_config_table(cursor) -> None:
    """Create the persistent key-value configuration table."""
    cursor.execute(
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
    with _connection() as cursor:
        cursor.execute(
            """
            INSERT INTO users (ig_username, telegram_chat_id)
            VALUES (%s, %s)
            ON CONFLICT (ig_username) DO UPDATE SET
                telegram_chat_id = EXCLUDED.telegram_chat_id
            """,
            (username, telegram_chat_id),
        )


def get_telegram_id(ig_username: str) -> str | None:
    """Return the Telegram chat ID linked to an Instagram username."""
    username = _normalize_username(ig_username)
    with _connection() as cursor:
        cursor.execute(
            "SELECT telegram_chat_id FROM users WHERE ig_username = %s",
            (username,),
        )
        row = cursor.fetchone()
    return str(row["telegram_chat_id"]) if row else None


def get_user_stats(ig_username: str) -> dict | None:
    """Return the complete user row for an Instagram username."""
    username = _normalize_username(ig_username)
    with _connection() as cursor:
        cursor.execute(
            "SELECT * FROM users WHERE ig_username = %s",
            (username,),
        )
        row = cursor.fetchone()
    return _row_to_dict(row)


def get_user_by_chat_id(telegram_chat_id: str) -> dict | None:
    """Return the registered user row for a Telegram chat ID."""
    with _connection() as cursor:
        cursor.execute(
            "SELECT * FROM users WHERE telegram_chat_id = %s",
            (telegram_chat_id,),
        )
        row = cursor.fetchone()
    return _row_to_dict(row)


def delete_user(ig_username: str) -> None:
    """Delete a user registration by Instagram username."""
    username = _normalize_username(ig_username)
    with _connection() as cursor:
        cursor.execute("DELETE FROM users WHERE ig_username = %s", (username,))


def replace_followers(followers: list[dict]) -> None:
    """Atomically replace the entire follower cache with the given list."""
    rows = [
        (str(item["id"]), _normalize_username(str(item.get("username", ""))))
        for item in followers
        if item.get("id") and item.get("username")
    ]
    with _connection() as cursor:
        cursor.execute("DELETE FROM followers")
        if rows:
            cursor.executemany(
                """
                INSERT INTO followers (ig_user_id, ig_username, updated_at)
                VALUES (%s, %s, CURRENT_TIMESTAMP)
                """,
                rows,
            )


def is_follower_in_cache(ig_user_id: str) -> bool:
    """Return whether a follower row exists in the cache, regardless of age."""
    with _connection() as cursor:
        cursor.execute(
            "SELECT 1 FROM followers WHERE ig_user_id = %s",
            (ig_user_id,),
        )
        row = cursor.fetchone()
    return row is not None


def get_followers_count() -> int:
    """Return the number of followers currently cached."""
    with _connection() as cursor:
        cursor.execute("SELECT COUNT(*) AS total FROM followers")
        row = cursor.fetchone()
    return int(row["total"])


def get_last_sync_time() -> str | None:
    """Return the persisted timestamp of the most recent follower sync."""
    return get_config("last_follower_sync")


def set_config(key: str, value: str) -> None:
    """Persist a configuration value by key."""
    with _connection() as cursor:
        cursor.execute(
            """
            INSERT INTO config (key, value, updated_at)
            VALUES (%s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (key) DO UPDATE SET
                value = EXCLUDED.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (key, value),
        )


def get_config(key: str) -> str | None:
    """Return a persisted configuration value by key."""
    with _connection() as cursor:
        cursor.execute(
            "SELECT value FROM config WHERE key = %s",
            (key,),
        )
        row = cursor.fetchone()
    return str(row["value"]) if row and row["value"] is not None else None


def is_already_processed(media_id: str) -> bool:
    """Return whether a media ID already has a processed record."""
    with _connection() as cursor:
        cursor.execute(
            "SELECT 1 FROM processed WHERE media_id = %s",
            (media_id,),
        )
        row = cursor.fetchone()
    return row is not None


def mark_processed(media_id: str, ig_username: str, status: str) -> None:
    """Insert a processed media record if one does not already exist."""
    username = _normalize_username(ig_username)
    with _connection() as cursor:
        cursor.execute(
            """
            INSERT INTO processed (media_id, ig_username, status)
            VALUES (%s, %s, %s)
            ON CONFLICT (media_id) DO NOTHING
            """,
            (media_id, username, status),
        )


def get_pending_unregistered(ig_username: str) -> bool:
    """Return whether a user previously tagged before registering."""
    username = _normalize_username(ig_username)
    with _connection() as cursor:
        cursor.execute(
            """
            SELECT 1 FROM processed
            WHERE ig_username = %s AND status = 'not_registered'
            LIMIT 1
            """,
            (username,),
        )
        row = cursor.fetchone()
    return row is not None


def get_last_delivery_time(telegram_chat_id: str) -> float | None:
    """Return the Unix timestamp of a chat's most recent delivery."""
    with _connection() as cursor:
        cursor.execute(
            """
            SELECT last_delivery_at
            FROM users
            WHERE telegram_chat_id = %s
            """,
            (telegram_chat_id,),
        )
        row = cursor.fetchone()
    return _timestamp_to_unix(row["last_delivery_at"]) if row else None


def try_reserve_delivery(
    telegram_chat_id: str, window_seconds: int
) -> tuple[bool, int]:
    """Atomically reserve a delivery slot for a chat.

    Returns ``(allowed, remaining_seconds)``. When allowed, the user's
    ``last_delivery_at`` is moved forward to ``CURRENT_TIMESTAMP`` so
    concurrent attempts inside the same rate-limit window are rejected.
    """
    with _connection() as cursor:
        cursor.execute(
            """
            UPDATE users
            SET last_delivery_at = CURRENT_TIMESTAMP
            WHERE telegram_chat_id = %s
              AND (last_delivery_at IS NULL
                   OR last_delivery_at <= NOW() - INTERVAL '%s seconds')
            """,
            (telegram_chat_id, window_seconds),
        )
        if cursor.rowcount > 0:
            return True, 0
        cursor.execute(
            "SELECT last_delivery_at FROM users WHERE telegram_chat_id = %s",
            (telegram_chat_id,),
        )
        row = cursor.fetchone()
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
    with _connection() as cursor:
        cursor.execute(
            """
            UPDATE users
            SET last_delivery_at = CURRENT_TIMESTAMP,
                total_delivered = total_delivered + 1
            WHERE ig_username = %s
            """,
            (username,),
        )


def get_stats_summary() -> dict:
    """Return aggregate system counters for admin and health views."""
    with _connection() as cursor:
        cursor.execute("SELECT COUNT(*) AS total FROM users")
        users = cursor.fetchone()
        cursor.execute(
            "SELECT COALESCE(SUM(total_delivered), 0) AS total FROM users"
        )
        delivered = cursor.fetchone()
        cursor.execute(
            "SELECT COUNT(*) AS total FROM processed WHERE status = 'failed'"
        )
        failed = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) AS total FROM followers")
        followers = cursor.fetchone()
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
    with _connection() as cursor:
        cursor.execute(
            """
            INSERT INTO logs (level, event_type, ig_username, detail)
            VALUES (%s, %s, %s, %s)
            """,
            (level, event_type, username, detail),
        )


def get_recent_logs(limit: int = 10) -> list[dict]:
    """Return the most recent log rows in reverse chronological order."""
    with _connection() as cursor:
        cursor.execute(
            """
            SELECT * FROM logs
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        )
        rows = cursor.fetchall()
    return [dict(row) for row in rows]


def get_recent_users(limit: int = 10) -> list[dict]:
    """Return the most recently registered users."""
    with _connection() as cursor:
        cursor.execute(
            """
            SELECT * FROM users
            ORDER BY registered_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        )
        rows = cursor.fetchall()
    return [dict(row) for row in rows]


def cleanup_old_data() -> None:
    """Delete old logs and processed media records."""
    with _connection() as cursor:
        cursor.execute("DELETE FROM logs WHERE created_at < NOW() - INTERVAL '30 days'")
        cursor.execute(
            "DELETE FROM processed WHERE processed_at < NOW() - INTERVAL '7 days'"
        )
