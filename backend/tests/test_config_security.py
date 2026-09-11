"""SECRET_KEY configuration security tests.

Production must refuse to start without a strong secret; DEBUG mode keeps
local development easy; the secret never appears in responses or logs.
"""

import pytest
from pydantic import ValidationError

from app.config import MIN_SECRET_KEY_LENGTH, Settings

WEAK_DEFAULT = "change-me-to-a-long-random-string"
STRONG = "a" * 40


def _settings(**overrides) -> Settings:
    # _env_file=None isolates from backend/.env; explicit kwargs still take
    # precedence over environment variables (conftest sets a test SECRET_KEY
    # and CORS_ORIGINS).
    defaults = {
        "SECRET_KEY": STRONG,
        "CORS_ORIGINS": "https://app.example.com",
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


# ---------------------------------------------------------------------------
# Production: fail fast unless a strong SECRET_KEY is configured
# ---------------------------------------------------------------------------


def test_production_with_valid_secret_key_starts():
    settings = _settings(DEBUG=False)
    assert settings.SECRET_KEY == STRONG


def test_production_with_missing_secret_key_fails_fast():
    with pytest.raises(ValidationError) as excinfo:
        _settings(DEBUG=False, SECRET_KEY=None)
    assert "SECRET_KEY" in str(excinfo.value)


def test_production_with_weak_default_secret_fails_fast():
    with pytest.raises(ValidationError):
        _settings(DEBUG=False, SECRET_KEY=WEAK_DEFAULT)


def test_production_with_short_secret_fails_fast():
    with pytest.raises(ValidationError):
        _settings(DEBUG=False, SECRET_KEY="short-secret")
    with pytest.raises(ValidationError):
        _settings(DEBUG=False, SECRET_KEY="x" * (MIN_SECRET_KEY_LENGTH - 1))


# ---------------------------------------------------------------------------
# Development: convenient, but the generated secret is never the weak default
# ---------------------------------------------------------------------------


def test_development_with_missing_secret_key_generates_random():
    settings = _settings(DEBUG=True, SECRET_KEY=None)
    assert settings.SECRET_KEY is not None
    assert len(settings.SECRET_KEY) == 64
    assert settings.SECRET_KEY != WEAK_DEFAULT


def test_development_with_weak_default_generates_random():
    settings = _settings(DEBUG=True, SECRET_KEY=WEAK_DEFAULT)
    assert settings.SECRET_KEY != WEAK_DEFAULT
    assert len(settings.SECRET_KEY) >= MIN_SECRET_KEY_LENGTH


def test_development_with_explicit_strong_secret_preserved():
    settings = _settings(DEBUG=True, SECRET_KEY=STRONG)
    assert settings.SECRET_KEY == STRONG


# ---------------------------------------------------------------------------
# CORS: production fails fast on permissive or unset origins
# ---------------------------------------------------------------------------


def test_production_rejects_wildcard_cors():
    with pytest.raises(ValidationError) as excinfo:
        _settings(DEBUG=False, CORS_ORIGINS="*")
    assert "CORS_ORIGINS" in str(excinfo.value)


def test_production_rejects_dev_default_cors():
    with pytest.raises(ValidationError) as excinfo:
        _settings(DEBUG=False, CORS_ORIGINS="http://localhost:3010,http://localhost:3011")
    assert "CORS_ORIGINS" in str(excinfo.value)


def test_production_rejects_empty_cors():
    with pytest.raises(ValidationError):
        _settings(DEBUG=False, CORS_ORIGINS="")


def test_production_rejects_non_http_cors_origin():
    with pytest.raises(ValidationError):
        _settings(DEBUG=False, CORS_ORIGINS="file:///tmp/app,https://app.example.com")


def test_production_accepts_explicit_origins():
    settings = _settings(DEBUG=False, CORS_ORIGINS="https://app.example.com,https://admin.example.com")
    assert settings.cors_origin_list == [
        "https://app.example.com",
        "https://admin.example.com",
    ]


def test_production_rejects_wildcard_even_with_explicit_origins():
    with pytest.raises(ValidationError):
        _settings(DEBUG=False, CORS_ORIGINS="https://app.example.com,*")


def test_development_can_keep_localhost_defaults():
    settings = _settings(DEBUG=True, CORS_ORIGINS="http://localhost:3010,http://localhost:3011")
    assert settings.cors_origin_list == ["http://localhost:3010", "http://localhost:3011"]


def test_development_still_rejects_wildcard():
    # Credentials are always in use; "*" is refused in every mode.
    with pytest.raises(ValidationError):
        _settings(DEBUG=True, CORS_ORIGINS="*")


# ---------------------------------------------------------------------------
# The secret never leaks through responses or logs on exercised paths
# ---------------------------------------------------------------------------


def test_secret_key_not_in_api_responses_or_logs(client, caplog):
    import logging

    caplog.set_level(logging.DEBUG)
    with caplog.at_level(logging.DEBUG):
        registered = client.post(
            "/api/v1/auth/register",
            json={"email": "leak@example.com", "password": "password123", "full_name": "Leak"},
        )
        token = registered.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        login = client.post("/api/v1/auth/login", json={"email": "leak@example.com", "password": "password123"})
        me = client.get("/api/v1/auth/me", headers=headers)
        forgot = client.post("/api/v1/auth/forgot-password", json={"email": "leak@example.com"})

    secret = "test-secret-key-not-for-production"
    for resp in (registered, login, me, forgot):
        assert secret not in resp.text, f"SECRET_KEY leaked in response: {resp.request.url}"
    assert secret not in caplog.text
