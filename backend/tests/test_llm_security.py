"""LLM / provider security: errors never leak URLs, keys or internals.

The provider-facing error detail is logged server-side only; the exception
that travels through jobs into API responses is always generic.
"""

import httpx
import pytest

from app.services.ai.llm import LLMClient, LLMError


class _FakeFailingClient:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, *args, **kwargs):
        raise httpx.ConnectError(
            "connect failed https://api.x.ai/v1/chat/completions with key sk-leak-test"
        )


class _FakeBadShapeClient:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, *args, **kwargs):
        class _Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return {"unexpected": "shape"}

        return _Resp()


def _client():
    return LLMClient(
        api_key="sk-not-a-real-key",
        base_url="https://api.x.ai/v1",
        model="grok-test",
    )


def test_provider_http_error_is_generic(monkeypatch):
    monkeypatch.setattr("app.services.ai.llm.httpx.Client", lambda *a, **k: _FakeFailingClient())
    with pytest.raises(LLMError) as excinfo:
        _client().chat("sys", "user")
    message = str(excinfo.value)
    assert message == "LLM request failed"
    assert "api.x.ai" not in message
    assert "sk-leak-test" not in message


def test_provider_bad_shape_is_generic(monkeypatch):
    monkeypatch.setattr("app.services.ai.llm.httpx.Client", lambda *a, **k: _FakeBadShapeClient())
    with pytest.raises(LLMError) as excinfo:
        _client().chat("sys", "user")
    assert str(excinfo.value) == "Unexpected LLM response"


def test_invalid_json_is_generic(monkeypatch):
    monkeypatch.setattr("app.services.ai.llm.httpx.Client", lambda *a, **k: _FakeBadShapeClient())
    with pytest.raises(LLMError) as excinfo:
        _client().chat_json("sys", "user")
    assert "api.x.ai" not in str(excinfo.value)
    assert "sk-not-a-real-key" not in str(excinfo.value)


def test_api_key_never_in_provider_logs(monkeypatch, caplog):
    import logging

    monkeypatch.setattr("app.services.ai.llm.httpx.Client", lambda *a, **k: _FakeFailingClient())
    caplog.set_level(logging.ERROR)
    with pytest.raises(LLMError):
        _client().chat("sys", "user")
    assert "sk-not-a-real-key" not in caplog.text
