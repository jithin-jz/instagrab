"""End-to-end tests for the Instagram webhook HTTP endpoint."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import health, instagram


@pytest.fixture
def client(fresh_db, monkeypatch):
    """Build a minimal FastAPI test app without the full lifespan/bot."""
    captured: list = []

    def sync_spawn(coro):
        # Just capture the coroutine for inspection; do not await it.
        captured.append(coro)

    monkeypatch.setattr("app.routers.instagram.spawn_background", sync_spawn)

    app = FastAPI()
    app.include_router(health.router)
    app.include_router(instagram.router)
    test_client = TestClient(app)
    test_client._captured = captured  # type: ignore[attr-defined]
    return test_client


def _sign(body: bytes, secret: str = "test-app-secret") -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_verify_handshake_succeeds(client) -> None:
    response = client.get(
        "/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "test-verify-token",
            "hub.challenge": "12345",
        },
    )
    assert response.status_code == 200
    assert response.json() == 12345


def test_verify_handshake_wrong_token_rejected(client) -> None:
    response = client.get(
        "/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong",
            "hub.challenge": "12345",
        },
    )
    assert response.status_code == 403


def test_post_invalid_signature_rejected(client) -> None:
    body = json.dumps({"object": "instagram", "entry": []}).encode()
    response = client.post(
        "/webhook",
        content=body,
        headers={"X-Hub-Signature-256": "sha256=deadbeef"},
    )
    assert response.status_code == 401


def test_post_oversize_rejected(client) -> None:
    body = b"x" * (3 * 1024 * 1024)
    response = client.post(
        "/webhook",
        content=body,
        headers={
            "X-Hub-Signature-256": _sign(body),
            "Content-Length": str(len(body)),
        },
    )
    assert response.status_code == 413


def test_post_valid_payload_queues_handler(client) -> None:
    body = json.dumps(
        {
            "object": "instagram",
            "entry": [
                {
                    "id": "ig",
                    "time": 0,
                    "changes": [
                        {"field": "mentions", "value": {"media_id": "mid_42"}}
                    ],
                }
            ],
        }
    ).encode()
    response = client.post(
        "/webhook",
        content=body,
        headers={"X-Hub-Signature-256": _sign(body)},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    captured = client._captured  # type: ignore[attr-defined]
    assert len(captured) == 1
    # Verify a coroutine was spawned (we don't await it in tests)
    assert hasattr(captured[0], "__await__")


def test_post_invalid_json_rejected(client) -> None:
    body = b"not json"
    response = client.post(
        "/webhook",
        content=body,
        headers={"X-Hub-Signature-256": _sign(body)},
    )
    assert response.status_code == 400


def test_health_endpoint(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "running"
    assert "total_users" in data
    assert "followers_cached" in data
