"""Tests for database persistence and rate-limit reservation."""

from __future__ import annotations

import time

from app.database import (
    get_telegram_id,
    get_user_by_chat_id,
    is_already_processed,
    mark_processed,
    replace_followers,
    save_user,
    try_reserve_delivery,
    update_delivery_stats,
    is_follower_in_cache,
)


def test_save_and_lookup_user(fresh_db) -> None:
    save_user("AliceTest", "111")
    assert get_telegram_id("alicetest") == "111"
    user = get_user_by_chat_id("111")
    assert user is not None
    assert user["ig_username"] == "alicetest"
    assert user["total_delivered"] == 0


def test_processed_idempotent(fresh_db) -> None:
    mark_processed("media_1", "alice", "delivered")
    mark_processed("media_1", "alice", "delivered")
    assert is_already_processed("media_1") is True
    assert is_already_processed("media_2") is False


def test_replace_followers_overwrites_cache(fresh_db) -> None:
    replace_followers([{"id": "1", "username": "alice"}, {"id": "2", "username": "bob"}])
    assert is_follower_in_cache("1") is True
    assert is_follower_in_cache("2") is True
    replace_followers([{"id": "3", "username": "carol"}])
    assert is_follower_in_cache("1") is False
    assert is_follower_in_cache("3") is True


def test_rate_limit_first_call_allowed(fresh_db) -> None:
    save_user("alice", "555")
    allowed, remaining = try_reserve_delivery("555", window_seconds=60)
    assert allowed is True
    assert remaining == 0


def test_rate_limit_second_call_blocked(fresh_db) -> None:
    save_user("alice", "555")
    first_allowed, _ = try_reserve_delivery("555", window_seconds=60)
    second_allowed, remaining = try_reserve_delivery("555", window_seconds=60)
    assert first_allowed is True
    assert second_allowed is False
    assert 1 <= remaining <= 60


def test_rate_limit_after_window_expires(fresh_db) -> None:
    save_user("alice", "555")
    try_reserve_delivery("555", window_seconds=1)
    time.sleep(1.05)
    allowed, _ = try_reserve_delivery("555", window_seconds=1)
    assert allowed is True


def test_rate_limit_unknown_chat_allowed(fresh_db) -> None:
    allowed, remaining = try_reserve_delivery("does-not-exist", window_seconds=60)
    assert allowed is True
    assert remaining == 0


def test_update_delivery_stats_increments_total(fresh_db) -> None:
    save_user("alice", "111")
    update_delivery_stats("alice")
    update_delivery_stats("alice")
    user = get_user_by_chat_id("111")
    assert user is not None
    assert user["total_delivered"] == 2
