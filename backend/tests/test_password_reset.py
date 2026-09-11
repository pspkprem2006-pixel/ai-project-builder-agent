"""Password-reset security regression tests.

Covers non-enumeration, production vs DEBUG token exposure, and the reset
lifecycle (valid / invalid / expired / single-use tokens).
"""

import uuid
from datetime import UTC, datetime, timedelta

import app.api.auth as auth_module
from app.database import SessionLocal
from app.models.user import User

GENERIC = "If the account exists, a password reset email has been sent."


def _register(client, prefix: str) -> str:
    email = f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "full_name": "Reset Test"},
    )
    assert resp.status_code == 201, resp.text
    return email


def _stored_token(email: str) -> str | None:
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email).first()
        return user.reset_token


def _enable_dev_mode(monkeypatch) -> None:
    monkeypatch.setattr(auth_module.settings, "DEBUG", True)


def _smtp_success(monkeypatch) -> None:
    monkeypatch.setattr(auth_module, "send_reset_email", lambda to_email, reset_link: True)


# ---------------------------------------------------------------------------
# Production behavior (DEBUG off): never expose the token, never enumerate
# ---------------------------------------------------------------------------


def test_production_smtp_unavailable_never_exposes_token(client):
    email = _register(client, "prod")
    resp = client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert resp.status_code == 200
    body = resp.json()
    assert body["detail"] == GENERIC
    assert body["reset_token"] is None
    stored = _stored_token(email)
    assert stored is not None
    assert stored not in resp.text


def test_production_smtp_configured_still_generic(client, monkeypatch):
    email = _register(client, "prodsmtp")
    _smtp_success(monkeypatch)
    resp = client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert resp.status_code == 200
    body = resp.json()
    assert body["detail"] == GENERIC
    assert body["reset_token"] is None


def test_production_unknown_email_generic(client):
    resp = client.post("/api/v1/auth/forgot-password", json={"email": "missing@example.com"})
    assert resp.status_code == 200
    assert resp.json()["detail"] == GENERIC
    assert resp.json()["reset_token"] is None


def test_production_responses_indistinguishable(client, monkeypatch):
    missing = client.post("/api/v1/auth/forgot-password", json={"email": "missing@example.com"}).json()
    existing_email = _register(client, "enum")
    existing = client.post("/api/v1/auth/forgot-password", json={"email": existing_email}).json()
    assert existing == missing


def test_production_smtp_success_response_indistinguishable(client, monkeypatch):
    _smtp_success(monkeypatch)
    missing = client.post("/api/v1/auth/forgot-password", json={"email": "missing@example.com"}).json()
    email = _register(client, "enumok")
    existing = client.post("/api/v1/auth/forgot-password", json={"email": email}).json()
    assert existing == missing


# ---------------------------------------------------------------------------
# Development behavior (DEBUG on): token exposed ONLY when SMTP is unavailable
# ---------------------------------------------------------------------------


def test_dev_mode_smtp_unavailable_returns_token(client, monkeypatch):
    _enable_dev_mode(monkeypatch)
    email = _register(client, "dev")
    resp = client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert resp.status_code == 200
    body = resp.json()
    assert body["reset_token"]
    assert body["reset_token"] == _stored_token(email)


def test_dev_mode_smtp_available_does_not_return_token(client, monkeypatch):
    _enable_dev_mode(monkeypatch)
    _smtp_success(monkeypatch)
    email = _register(client, "devsmtp")
    resp = client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert resp.status_code == 200
    assert resp.json()["reset_token"] is None


def test_reset_tokens_are_random_and_long(client, monkeypatch):
    _enable_dev_mode(monkeypatch)
    email = _register(client, "rand")
    first = client.post("/api/v1/auth/forgot-password", json={"email": email}).json()["reset_token"]
    second = client.post("/api/v1/auth/forgot-password", json={"email": email}).json()["reset_token"]
    assert first != second
    assert len(first) >= 43
    assert len(second) >= 43


# ---------------------------------------------------------------------------
# Reset lifecycle
# ---------------------------------------------------------------------------


def test_reset_flow_with_valid_token(client, monkeypatch):
    _enable_dev_mode(monkeypatch)
    email = _register(client, "flow")
    token = client.post("/api/v1/auth/forgot-password", json={"email": email}).json()["reset_token"]
    resp = client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": "newpassword1"})
    assert resp.status_code == 200
    assert client.post("/api/v1/auth/login", json={"email": email, "password": "newpassword1"}).status_code == 200
    assert client.post("/api/v1/auth/login", json={"email": email, "password": "password123"}).status_code == 401
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email).first()
        assert user.reset_token is None
        assert user.reset_token_expires is None


def test_reset_with_invalid_token(client):
    resp = client.post("/api/v1/auth/reset-password", json={"token": "bogus-token", "new_password": "newpassword1"})
    assert resp.status_code == 400


def test_reset_with_expired_token(client):
    email = _register(client, "expired")
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email).first()
        user.reset_token = "stale-token"
        user.reset_token_expires = datetime.now(UTC) - timedelta(hours=1)
        db.commit()
    resp = client.post("/api/v1/auth/reset-password", json={"token": "stale-token", "new_password": "newpassword1"})
    assert resp.status_code == 400


def test_reset_token_is_single_use(client, monkeypatch):
    _enable_dev_mode(monkeypatch)
    email = _register(client, "once")
    token = client.post("/api/v1/auth/forgot-password", json={"email": email}).json()["reset_token"]
    first = client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": "newpassword1"})
    assert first.status_code == 200
    second = client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": "newpassword2"})
    assert second.status_code == 400
    assert client.post("/api/v1/auth/login", json={"email": email, "password": "newpassword1"}).status_code == 200
    assert client.post("/api/v1/auth/login", json={"email": email, "password": "newpassword2"}).status_code == 401
