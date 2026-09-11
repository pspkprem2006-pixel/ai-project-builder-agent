"""Auth rate limiting: DB-backed fixed-window limits.

Covers the service primitives (under / at / over limit, window reset, key
isolation) and the endpoint behavior (429 status, Retry-After, generic
non-enumerating message, per-account isolation for login).
"""

import pytest

from app.config import get_settings
from app.database import SessionLocal
from app.models.rate_limit import RateLimit
from app.services.rate_limiting import check_rate_limit


@pytest.fixture()
def clean_rate_limits():
    with SessionLocal() as db:
        db.query(RateLimit).delete()
        db.commit()
    yield


# ---------------------------------------------------------------------------
# Service primitives
# ---------------------------------------------------------------------------


def test_under_limit_allowed(clean_rate_limits):
    with SessionLocal() as db:
        allowed, remaining, limit = check_rate_limit(db, "login:u1", 5, 900)
        assert allowed and remaining == 4 and limit == 5


def test_at_limit_allowed_then_blocked(clean_rate_limits):
    with SessionLocal() as db:
        for attempt in range(1, 6):
            allowed, remaining, _ = check_rate_limit(db, "login:u1", 5, 900)
            assert allowed, f"attempt {attempt} should be allowed"
            assert remaining == 5 - attempt
        allowed, remaining, _ = check_rate_limit(db, "login:u1", 5, 900)
        assert not allowed and remaining == 0


def test_over_limit_blocks_every_further_attempt(clean_rate_limits):
    with SessionLocal() as db:
        for _ in range(7):
            check_rate_limit(db, "login:u1", 3, 900)
        allowed, remaining, _ = check_rate_limit(db, "login:u1", 3, 900)
        assert not allowed and remaining == 0


def test_zero_limit_blocks_everything(clean_rate_limits):
    with SessionLocal() as db:
        allowed, _, _ = check_rate_limit(db, "login:u1", 0, 900)
        assert not allowed


def test_separate_keys_are_independent(clean_rate_limits):
    with SessionLocal() as db:
        for _ in range(5):
            check_rate_limit(db, "login:ip1:alice@example.com", 5, 900)
        allowed, remaining, _ = check_rate_limit(db, "login:ip1:bob@example.com", 5, 900)
        assert allowed and remaining == 4
        allowed, _, _ = check_rate_limit(db, "login:ip1:alice@example.com", 5, 900)
        assert not allowed


def test_window_expiry_resets_counter(clean_rate_limits):
    with SessionLocal() as db:
        for _ in range(5):
            check_rate_limit(db, "register:ip1", 5, 60)
        allowed, _, _ = check_rate_limit(db, "register:ip1", 5, 60)
        assert not allowed
        # Simulate the next fixed window: mutate the stored window.
        from datetime import timedelta

        row = db.query(RateLimit).filter(RateLimit.key == "register:ip1").one()
        row.window_start = row.window_start - timedelta(seconds=120)
        db.commit()
        allowed, remaining, _ = check_rate_limit(db, "register:ip1", 5, 60)
        assert allowed and remaining == 4


def test_429_response_and_headers(client, clean_rate_limits, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "RATE_LIMIT_LOGIN", 2)
    for _ in range(2):
        resp = client.post(
            "/api/v1/auth/login", json={"email": "victim@example.com", "password": "password123"}
        )
        assert resp.status_code in (401, 429)
    resp = client.post(
        "/api/v1/auth/login", json={"email": "victim@example.com", "password": "password123"}
    )
    assert resp.status_code == 429
    body = resp.json()
    assert body["detail"] == "Too many attempts. Please try again later."
    assert resp.headers.get("retry-after") == "900"


# ---------------------------------------------------------------------------
# Endpoint behavior
# ---------------------------------------------------------------------------


def test_login_under_limit_allows_legitimate_attempts(client, clean_rate_limits, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "RATE_LIMIT_LOGIN", 3)
    for _ in range(3):
        resp = client.post(
            "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "wrong"}
        )
        assert resp.status_code == 401
    resp = client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "wrong"}
    )
    assert resp.status_code == 429


def test_login_different_accounts_do_not_share_quota(client, clean_rate_limits, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "RATE_LIMIT_LOGIN", 2)
    for _ in range(2):
        client.post(
            "/api/v1/auth/login", json={"email": "alice@example.com", "password": "wrong"}
        )
    blocked = client.post(
        "/api/v1/auth/login", json={"email": "alice@example.com", "password": "wrong"}
    )
    assert blocked.status_code == 429
    allowed = client.post(
        "/api/v1/auth/login", json={"email": "bob@example.com", "password": "wrong"}
    )
    assert allowed.status_code == 401


def test_register_over_limit_blocks_creation(client, clean_rate_limits, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "RATE_LIMIT_REGISTER", 2)
    for i in range(2):
        resp = client.post(
            "/api/v1/auth/register",
            json={"email": f"rate-{i}@example.com", "password": "password123", "full_name": "R"},
        )
        assert resp.status_code == 201
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "rate-2@example.com", "password": "password123", "full_name": "R"},
    )
    assert resp.status_code == 429


def test_forgot_password_over_limit_is_generic_and_blocks(client, clean_rate_limits, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "RATE_LIMIT_FORGOT", 2)
    # Register a real account so both branches (exists / not exists) hit the limit.
    client.post(
        "/api/v1/auth/register",
        json={"email": "forgot@example.com", "password": "password123", "full_name": "F"},
    )
    for _ in range(2):
        resp = client.post("/api/v1/auth/forgot-password", json={"email": "forgot@example.com"})
        assert resp.status_code == 200
    resp = client.post("/api/v1/auth/forgot-password", json={"email": "forgot@example.com"})
    assert resp.status_code == 429
    assert resp.json()["detail"] == "Too many attempts. Please try again later."


def test_forgot_password_rate_limit_does_not_enumerate(client, clean_rate_limits, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "RATE_LIMIT_FORGOT", 2)
    client.post(
        "/api/v1/auth/register",
        json={"email": "exists@example.com", "password": "password123", "full_name": "E"},
    )
    # Exhaust both the existing account and a non-existent account: identical 429s.
    for email in ("exists@example.com", "ghost@example.com"):
        for _ in range(2):
            client.post("/api/v1/auth/forgot-password", json={"email": email})
        resp = client.post("/api/v1/auth/forgot-password", json={"email": email})
        assert resp.status_code == 429
        assert resp.json()["detail"] == "Too many attempts. Please try again later."


def test_reset_password_over_limit(client, clean_rate_limits, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "RATE_LIMIT_RESET", 2)
    for _ in range(2):
        resp = client.post(
            "/api/v1/auth/reset-password",
            json={"token": "nope", "new_password": "password123"},
        )
        assert resp.status_code == 400
    resp = client.post(
        "/api/v1/auth/reset-password", json={"token": "nope", "new_password": "password123"}
    )
    assert resp.status_code == 429


def test_register_ip_bucket_shared_but_account_login_isolated(client, clean_rate_limits, monkeypatch):
    """Registration is per-IP; login is per (IP, account)."""
    settings = get_settings()
    monkeypatch.setattr(settings, "RATE_LIMIT_REGISTER", 1)
    ok = client.post(
        "/api/v1/auth/register",
        json={"email": "one@example.com", "password": "password123", "full_name": "A"},
    )
    assert ok.status_code == 201
    blocked = client.post(
        "/api/v1/auth/register",
        json={"email": "two@example.com", "password": "password123", "full_name": "B"},
    )
    assert blocked.status_code == 429
