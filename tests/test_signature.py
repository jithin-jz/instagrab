"""Tests for the Instagram webhook HMAC signature verifier."""

from __future__ import annotations

import hashlib
import hmac

from app.routers.instagram import _verify_signature


def _signed(body: bytes, secret: str = "test-app-secret") -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_valid_signature_accepted() -> None:
    body = b'{"hello":"world"}'
    assert _verify_signature(body, _signed(body)) is True


def test_tampered_body_rejected() -> None:
    body = b'{"hello":"world"}'
    signature = _signed(body)
    assert _verify_signature(b'{"hello":"WORLD"}', signature) is False


def test_wrong_secret_rejected() -> None:
    body = b'{"hello":"world"}'
    bad_sig = _signed(body, secret="other-secret")
    assert _verify_signature(body, bad_sig) is False


def test_missing_prefix_rejected() -> None:
    body = b'{"hello":"world"}'
    digest = hmac.new(b"test-app-secret", body, hashlib.sha256).hexdigest()
    assert _verify_signature(body, digest) is False


def test_empty_signature_rejected() -> None:
    assert _verify_signature(b"x", "") is False
