"""Auth gate — HTTP and WebSocket.

The WebSocket cases exist because their absence let a real regression ship: an
app-level FastAPI dependency typed (request: Request) is also applied to
WebSocket routes, where it receives a WebSocket and raises TypeError before the
handler runs. That broke SSH, telnet, serial and local shell at once, and no
test noticed.
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("NTERM_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NTERM_AUTH_TOKEN", "test-token-123")
    for mod in list(sys.modules):
        if mod.startswith("app"):
            del sys.modules[mod]
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


TOK = {"X-NTerm-Token": "test-token-123"}


# ── HTTP ──────────────────────────────────────────────────────────────────
def test_api_requires_a_token(client):
    assert client.get("/api/customers").status_code == 401


def test_api_accepts_a_valid_token(client):
    assert client.get("/api/customers", headers=TOK).status_code == 200


def test_api_rejects_a_wrong_token(client):
    assert client.get("/api/customers", headers={"X-NTerm-Token": "nope"}).status_code == 401


def test_health_stays_open_for_the_container_probe(client):
    assert client.get("/api/health").status_code == 200


def test_destructive_verbs_are_guarded_too(client):
    """CORS does not stop a no-cors POST; the token has to."""
    assert client.delete("/api/customers/1").status_code == 401


def test_spa_loads_without_a_token_and_carries_one(client):
    """Only meaningful once the frontend is built into app/static (the image
    build does this; a bare source checkout does not)."""
    from app.config import STATIC_DIR
    if not (STATIC_DIR / "index.html").exists():
        pytest.skip("frontend not built into app/static")
    r = client.get("/")
    assert r.status_code == 200
    assert 'name="nterm-token"' in r.text


# ── WebSocket: the regression that shipped ────────────────────────────────
def test_websocket_opens_with_a_valid_token(client):
    """The case that was broken. Must not raise TypeError."""
    with client.websocket_connect(
        "/ws/term/tab-1?session_id=1&token=test-token-123"
    ) as ws:
        msg = ws.receive_json()
        assert msg["type"] in ("status", "error")


def test_websocket_is_refused_without_a_token(client):
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/term/tab-1?session_id=1") as ws:
            ws.receive_json()


def test_websocket_is_refused_with_a_wrong_token(client):
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/term/tab-1?session_id=1&token=nope") as ws:
            ws.receive_json()
