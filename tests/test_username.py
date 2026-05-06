"""Tests for the Instagram username validator and normalizer."""

from __future__ import annotations

import pytest

from app.services.telegram_bot import _normalize_username, is_valid_username


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("foo", "foo"),
        ("  Foo  ", "foo"),
        ("@foo.bar", "foo.bar"),
        ("FOO_BAR", "foo_bar"),
    ],
)
def test_normalize_username(raw: str, expected: str) -> None:
    assert _normalize_username(raw) == expected


@pytest.mark.parametrize(
    "name",
    ["foo", "f", "f_o.o", "abc123", "a" * 30],
)
def test_valid_usernames(name: str) -> None:
    assert is_valid_username(name) is True


@pytest.mark.parametrize(
    "name",
    ["", " ", "a b", "a" * 31, "Foo", "foo!", "foo-bar", "@foo"],
)
def test_invalid_usernames(name: str) -> None:
    assert is_valid_username(name) is False
