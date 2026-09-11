"""Phase 13B — OpenRouter multi-model routing.

Covers: provider preset resolution, backend-only key selection, role model
resolution, the 21-agent + validation routing map, model precedence, fallback
chain ordering, bounded transient retries (429/503/timeout retry once; 401
never retries), error hygiene, OpenRouter request shape, deterministic
no-key behavior, provider metadata, action routing (_explain -> fast,
_analyze -> reasoning_secondary), and OpenAI/Grok backward compatibility.
"""

from __future__ import annotations

import logging
import types

import httpx
import pytest

from app.config import (
    LLM_PROVIDER_PRESETS,
    OPENROUTER_ROLE_FALLBACKS,
    OPENROUTER_ROLE_MODELS,
    get_settings,
)
from app.services.ai.agents import AGENT_KEYS, SECTION_MODEL_ROLES, run_pipeline
from app.services.ai.llm import LLMClient, LLMError, LLMNotConfiguredError
from tests.test_projects import PROJECT_PAYLOAD

EXPECTED_SECTION_MODEL_ROLES = {
    "analysis": "reasoning_primary",
    "domain_understanding": "reasoning_primary",
    "business_processes": "reasoning_primary",
    "technology_selection": "coding",
    "technology_evaluation": "reasoning_secondary",
    "design_decisions": "reasoning_secondary",
    "tradeoffs": "reasoning_secondary",
    "architecture": "reasoning_primary",
    "database": "coding",
    "api": "coding",
    "ui_ux": "fast",
    "security": "reasoning_secondary",
    "performance": "reasoning_secondary",
    "scalability": "reasoning_secondary",
    "cost_estimation": "fast",
    "business_risks": "reasoning_secondary",
    "roadmap": "reasoning_secondary",
    "product_evolution": "fast",
    "adr": "fast",
    "testing": "coding",
    "documentation": "fast",
    "validation_agent": "reasoning_primary",
}

ALL_ROLES = ("reasoning_primary", "reasoning_secondary", "coding", "fast")


@pytest.fixture
def llm_env(monkeypatch):
    """Pin environment for a test and rebuild the cached Settings.

    The cache is rebuilt before (so the test sees the pinned values) and
    after the test (so the polluted instance never leaks into later tests).

    All role model/fallback env vars are explicitly cleared to empty strings
    so they never bleed through from ``backend/.env`` via pydantic-settings.
    """
    _ROLE_ENV = (
        "REASONING_PRIMARY_MODEL",
        "REASONING_SECONDARY_MODEL",
        "CODING_MODEL",
        "FAST_MODEL",
        "REASONING_PRIMARY_FALLBACK_MODELS",
        "REASONING_SECONDARY_FALLBACK_MODELS",
        "CODING_FALLBACK_MODELS",
        "FAST_FALLBACK_MODELS",
    )

    def _apply(**env) -> None:
        for var in _ROLE_ENV:
            if var not in env:
                monkeypatch.setenv(var, "")
        for key, value in env.items():
            if value is None:
                monkeypatch.delenv(key, raising=False)
            else:
                monkeypatch.setenv(key, value)
        get_settings.cache_clear()

    yield _apply
    get_settings.cache_clear()


class _FakeResp:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://fake.test/chat/completions")
            raise httpx.HTTPStatusError(
                f"error {self.status_code}", request=request, response=self
            )

    def json(self):
        return self._payload


class _ScriptedClient:
    """Replays a scripted response sequence and records every request."""

    def __init__(self, steps):
        self.steps = list(steps)
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, headers=None, json=None):
        self.calls.append({"url": url, "headers": headers or {}, "json": json or {}})
        step = self.steps.pop(0)
        if "error" in step:
            raise step["error"]
        return _FakeResp(step["status"], step["payload"])


def _ok_payload() -> dict:
    return {"choices": [{"message": {"content": '{"ok": true}'}}]}


def _patch_transport(monkeypatch, client: _ScriptedClient) -> None:
    monkeypatch.setattr("app.services.ai.llm.httpx.Client", lambda *a, **k: client)


# ---------------------------------------------------------------------------
# A. Provider preset
# ---------------------------------------------------------------------------


def test_openrouter_preset_resolves(llm_env):
    llm_env(LLM_PROVIDER="openrouter", OPENROUTER_API_KEY="sk-or-test")
    assert LLM_PROVIDER_PRESETS["openrouter"]["base_url"] == "https://openrouter.ai/api/v1"
    assert LLMClient().base_url == "https://openrouter.ai/api/v1"


def test_openai_and_grok_presets_unchanged():
    assert LLM_PROVIDER_PRESETS["openai"] == {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-5.5",
    }
    assert LLM_PROVIDER_PRESETS["grok"] == {
        "base_url": "https://api.x.ai/v1",
        "model": "grok-4.5",
    }


# ---------------------------------------------------------------------------
# B. API key handling
# ---------------------------------------------------------------------------


def test_openrouter_prefers_its_own_key(llm_env):
    llm_env(
        LLM_PROVIDER="openrouter",
        OPENROUTER_API_KEY="sk-or-test",
        OPENAI_API_KEY="sk-oa-test",
    )
    assert LLMClient().api_key == "sk-or-test"


def test_openrouter_falls_back_to_openai_key(llm_env):
    llm_env(LLM_PROVIDER="openrouter", OPENROUTER_API_KEY="", OPENAI_API_KEY="sk-oa-test")
    assert LLMClient().api_key == "sk-oa-test"
    assert get_settings().llm_configured is True


def test_openai_provider_ignores_openrouter_key(llm_env):
    llm_env(
        LLM_PROVIDER="openai",
        OPENAI_API_KEY="sk-oa-test",
        OPENROUTER_API_KEY="sk-or-test",
    )
    assert LLMClient().api_key == "sk-oa-test"


def test_openrouter_without_key_not_configured(llm_env):
    llm_env(LLM_PROVIDER="openrouter", OPENROUTER_API_KEY="", OPENAI_API_KEY="")
    assert get_settings().llm_configured is False
    client = LLMClient()
    assert client.available is False
    with pytest.raises(LLMNotConfiguredError):
        client.chat("sys", "user")


# ---------------------------------------------------------------------------
# C. Role resolution
# ---------------------------------------------------------------------------


def test_all_four_roles_resolve_from_environment(llm_env):
    llm_env(
        LLM_PROVIDER="openrouter",
        OPENROUTER_API_KEY="sk-or-test",
        REASONING_PRIMARY_MODEL="rp-model",
        REASONING_SECONDARY_MODEL="rs-model",
        CODING_MODEL="cd-model",
        FAST_MODEL="ft-model",
    )
    assert LLMClient(model_role="reasoning_primary").model == "rp-model"
    assert LLMClient(model_role="reasoning_secondary").model == "rs-model"
    assert LLMClient(model_role="coding").model == "cd-model"
    assert LLMClient(model_role="fast").model == "ft-model"


def test_openrouter_role_defaults_when_unset(llm_env):
    llm_env(LLM_PROVIDER="openrouter", OPENROUTER_API_KEY="sk-or-test")
    for role in ALL_ROLES:
        assert LLMClient(model_role=role).model == OPENROUTER_ROLE_MODELS[role]


def test_non_openrouter_role_without_config_uses_provider_default(llm_env):
    llm_env(LLM_PROVIDER="openai", OPENAI_API_KEY="sk-oa-test", OPENAI_MODEL="gpt-default")
    assert LLMClient(model_role="reasoning_primary").model == "gpt-default"
    assert LLMClient(model_role="coding").model == "gpt-default"


# ---------------------------------------------------------------------------
# D. Section routing
# ---------------------------------------------------------------------------


def test_section_model_roles_mapping_exact():
    assert SECTION_MODEL_ROLES == EXPECTED_SECTION_MODEL_ROLES
    assert len(SECTION_MODEL_ROLES) == 22
    assert set(AGENT_KEYS) <= set(SECTION_MODEL_ROLES)
    assert SECTION_MODEL_ROLES["validation_agent"] == "reasoning_primary"
    assert len(AGENT_KEYS) == 21


# ---------------------------------------------------------------------------
# E. Model precedence
# ---------------------------------------------------------------------------


def test_explicit_model_beats_role_model(llm_env):
    llm_env(
        LLM_PROVIDER="openrouter",
        OPENROUTER_API_KEY="sk-or-test",
        REASONING_PRIMARY_MODEL="rp-model",
    )
    client = LLMClient(model="explicit-model", model_role="reasoning_primary")
    assert client.model == "explicit-model"
    assert client.model_chain == ["explicit-model"]


def test_role_model_beats_provider_default(llm_env):
    llm_env(
        LLM_PROVIDER="openrouter",
        OPENROUTER_API_KEY="sk-or-test",
        OPENAI_MODEL="default-model",
        REASONING_PRIMARY_MODEL="rp-model",
    )
    assert LLMClient(model_role="reasoning_primary").model == "rp-model"


def test_provider_default_when_no_role(llm_env):
    llm_env(LLM_PROVIDER="openai", OPENAI_API_KEY="sk-oa-test", OPENAI_MODEL="default-model")
    assert LLMClient().model == "default-model"
    assert LLMClient().model_chain == ["default-model"]


def test_preset_model_is_last_resort(llm_env):
    llm_env(LLM_PROVIDER="openai", OPENAI_API_KEY="sk-oa-test")
    assert LLMClient().model == "gpt-5.5"


def test_explicit_model_kwarg_backward_compat(llm_env):
    llm_env(LLM_PROVIDER="grok", OPENAI_API_KEY="sk-x-test")
    client = LLMClient(model="grok-custom")
    assert client.model == "grok-custom"
    assert client.base_url == "https://api.x.ai/v1"


# ---------------------------------------------------------------------------
# F. Fallback ordering
# ---------------------------------------------------------------------------


def test_fallback_chain_primary_then_fallbacks(monkeypatch, llm_env):
    llm_env(
        LLM_PROVIDER="openrouter",
        OPENROUTER_API_KEY="sk-or-test",
        FAST_MODEL="nano",
        FAST_FALLBACK_MODELS="super,ultra",
    )
    # Each model gets one transient failure then the chain advances; the
    # client retries each model once (1 retry per model), so the transcript
    # is nano, nano, super, super, ultra.
    fake = _ScriptedClient(
        [
            {"status": 503, "payload": None},
            {"status": 503, "payload": None},
            {"status": 429, "payload": None},
            {"status": 429, "payload": None},
            {"status": 200, "payload": _ok_payload()},
        ]
    )
    _patch_transport(monkeypatch, fake)
    client = LLMClient(model_role="fast")
    assert client.model == "nano"
    assert client.model_chain == ["nano", "super", "ultra"]
    assert client.chat_json("sys", "user") == {"ok": True}
    assert [c["json"]["model"] for c in fake.calls] == ["nano", "nano", "super", "super", "ultra"]


def test_openrouter_default_fallback_chains_configured():
    assert OPENROUTER_ROLE_FALLBACKS["reasoning_primary"] == [
        "nvidia/nemotron-3-nano-30b-a3b:free",
    ]
    assert OPENROUTER_ROLE_FALLBACKS["fast"] == ["nvidia/nemotron-3-super-120b-a12b:free"]


# ---------------------------------------------------------------------------
# G. Retry policy
# ---------------------------------------------------------------------------


def test_429_retries_once_then_succeeds(monkeypatch, llm_env):
    llm_env(LLM_PROVIDER="openrouter", OPENROUTER_API_KEY="sk-or-test", FAST_MODEL="nano")
    fake = _ScriptedClient(
        [
            {"status": 429, "payload": None},
            {"status": 200, "payload": _ok_payload()},
        ]
    )
    _patch_transport(monkeypatch, fake)
    assert LLMClient(model_role="fast").chat_json("sys", "user") == {"ok": True}
    assert [c["json"]["model"] for c in fake.calls] == ["nano", "nano"]


def test_503_retries_once_then_succeeds(monkeypatch, llm_env):
    llm_env(LLM_PROVIDER="openrouter", OPENROUTER_API_KEY="sk-or-test", FAST_MODEL="nano")
    fake = _ScriptedClient(
        [
            {"status": 503, "payload": None},
            {"status": 200, "payload": _ok_payload()},
        ]
    )
    _patch_transport(monkeypatch, fake)
    assert LLMClient(model_role="fast").chat_json("sys", "user") == {"ok": True}
    assert len(fake.calls) == 2


def test_timeout_retries_once(monkeypatch, llm_env):
    llm_env(LLM_PROVIDER="openrouter", OPENROUTER_API_KEY="sk-or-test", FAST_MODEL="nano")
    fake = _ScriptedClient(
        [
            {"error": httpx.ConnectError("connect failed")},
            {"status": 200, "payload": _ok_payload()},
        ]
    )
    _patch_transport(monkeypatch, fake)
    assert LLMClient(model_role="fast").chat_json("sys", "user") == {"ok": True}
    assert len(fake.calls) == 2


def test_non_transient_401_does_not_retry(monkeypatch, llm_env):
    llm_env(
        LLM_PROVIDER="openrouter",
        OPENROUTER_API_KEY="sk-or-test",
        FAST_MODEL="nano",
        FAST_FALLBACK_MODELS="super",
    )
    fake = _ScriptedClient([{"status": 401, "payload": {"error": {"message": "invalid key"}}}])
    _patch_transport(monkeypatch, fake)
    with pytest.raises(LLMError) as excinfo:
        LLMClient(model_role="fast").chat("sys", "user")
    assert str(excinfo.value) == "LLM request failed"
    assert len(fake.calls) == 1
    assert fake.calls[0]["json"]["model"] == "nano"


def test_non_transient_400_does_not_retry(monkeypatch, llm_env):
    llm_env(
        LLM_PROVIDER="openrouter",
        OPENROUTER_API_KEY="sk-or-test",
        FAST_MODEL="nano",
        FAST_FALLBACK_MODELS="super",
    )
    fake = _ScriptedClient([{"status": 400, "payload": {"error": {"message": "bad model"}}}])
    _patch_transport(monkeypatch, fake)
    with pytest.raises(LLMError) as excinfo:
        LLMClient(model_role="fast").chat("sys", "user")
    assert str(excinfo.value) == "LLM request failed"
    assert len(fake.calls) == 1


def test_chain_exhaustion_raises_generic_error(monkeypatch, llm_env):
    llm_env(
        LLM_PROVIDER="openrouter",
        OPENROUTER_API_KEY="sk-or-test",
        FAST_MODEL="nano",
        FAST_FALLBACK_MODELS="super",
    )
    fake = _ScriptedClient(
        [
            {"status": 503, "payload": None},
            {"status": 503, "payload": None},
            {"status": 503, "payload": None},
            {"status": 503, "payload": None},
        ]
    )
    _patch_transport(monkeypatch, fake)
    with pytest.raises(LLMError) as excinfo:
        LLMClient(model_role="fast").chat("sys", "user")
    assert str(excinfo.value) == "LLM request failed"
    assert len(fake.calls) == 4


# ---------------------------------------------------------------------------
# G2. Error hygiene
# ---------------------------------------------------------------------------


def test_error_hygiene_no_key_in_exception_or_logs(monkeypatch, caplog, llm_env):
    llm_env(
        LLM_PROVIDER="openrouter",
        OPENROUTER_API_KEY="sk-or-secret",
        FAST_MODEL="nano",
        FAST_FALLBACK_MODELS="",
    )
    fake = _ScriptedClient(
        [
            {"error": httpx.ConnectError("connect failed with key sk-or-secret")},
            {"error": httpx.ConnectError("connect failed with key sk-or-secret")},
            {"error": httpx.ConnectError("connect failed with key sk-or-secret")},
            {"error": httpx.ConnectError("connect failed with key sk-or-secret")},
        ]
    )
    _patch_transport(monkeypatch, fake)
    caplog.set_level(logging.WARNING)
    with pytest.raises(LLMError) as excinfo:
        LLMClient(model_role="fast").chat("sys", "user")
    assert str(excinfo.value) == "LLM request failed"
    assert "sk-or-secret" not in str(excinfo.value)
    assert "sk-or-secret" not in caplog.text


def test_invalid_json_error_stays_generic(monkeypatch, llm_env):
    llm_env(LLM_PROVIDER="openrouter", OPENROUTER_API_KEY="sk-or-secret", FAST_MODEL="nano")
    fake = _ScriptedClient(
        [{"status": 200, "payload": {"choices": [{"message": {"content": "not json at all"}}]}}]
    )
    _patch_transport(monkeypatch, fake)
    with pytest.raises(LLMError) as excinfo:
        LLMClient(model_role="fast").chat_json("sys", "user")
    assert str(excinfo.value) == "LLM did not return valid JSON"


# ---------------------------------------------------------------------------
# H. OpenRouter request shape
# ---------------------------------------------------------------------------


def test_openrouter_request_shape(monkeypatch, llm_env):
    llm_env(LLM_PROVIDER="openrouter", OPENROUTER_API_KEY="sk-or-shape", FAST_MODEL="nano")
    fake = _ScriptedClient([{"status": 200, "payload": _ok_payload()}])
    _patch_transport(monkeypatch, fake)
    LLMClient(model_role="fast").chat_json("sys", "user")
    call = fake.calls[0]
    assert call["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer sk-or-shape"
    assert call["json"]["model"] == "nano"
    assert "response_format" not in call["json"]


def test_response_format_is_opt_in(monkeypatch, llm_env):
    llm_env(LLM_PROVIDER="openrouter", OPENROUTER_API_KEY="sk-or-shape", FAST_MODEL="nano")
    fake = _ScriptedClient([{"status": 200, "payload": _ok_payload()}])
    _patch_transport(monkeypatch, fake)
    LLMClient(model_role="fast", response_format=True).chat_json("sys", "user")
    assert fake.calls[0]["json"]["response_format"] == {"type": "json_object"}


# ---------------------------------------------------------------------------
# I. No-key behavior (deterministic pipeline)
# ---------------------------------------------------------------------------


def test_pipeline_succeeds_deterministically_without_key(llm_env):
    llm_env(LLM_PROVIDER="openrouter", OPENROUTER_API_KEY="", OPENAI_API_KEY="")
    blueprint, provider = run_pipeline(dict(PROJECT_PAYLOAD))
    assert provider == "template"
    assert set(AGENT_KEYS) <= set(blueprint)
    assert "validation" in blueprint
    assert "deployment" in blueprint


# ---------------------------------------------------------------------------
# J. Provider metadata
# ---------------------------------------------------------------------------


class _RecordingLLM:
    """Fake LLMClient for pipeline-level tests; records model roles."""

    available = True
    instances: list[str] = []

    def __init__(self, *args, **kwargs):
        _RecordingLLM.instances.append(kwargs.get("model_role"))

    def chat_json(self, system, user, max_tokens=8192):
        return {"summary": "ok", "title": "ok"}


def test_openrouter_pipeline_provider_metadata(monkeypatch, llm_env):
    _RecordingLLM.instances = []
    llm_env(LLM_PROVIDER="openrouter", OPENROUTER_API_KEY="sk-or-test")
    monkeypatch.setattr("app.services.ai.agents.LLMClient", _RecordingLLM)
    blueprint, provider = run_pipeline(dict(PROJECT_PAYLOAD))
    assert provider == "openrouter"
    assert len(_RecordingLLM.instances) == 22
    assert set(_RecordingLLM.instances) == set(ALL_ROLES)
    assert _RecordingLLM.instances[-1] == "reasoning_primary"
    assert blueprint["metadata"]["domain_context"]["primary_domain"] == "hospital"


# ---------------------------------------------------------------------------
# K. Existing compatibility (OpenAI / Grok)
# ---------------------------------------------------------------------------


def test_grok_provider_still_works(llm_env):
    llm_env(LLM_PROVIDER="grok", OPENAI_API_KEY="sk-x-test", OPENAI_MODEL="grok-4.5")
    client = LLMClient()
    assert client.base_url == "https://api.x.ai/v1"
    assert client.model == "grok-4.5"
    assert client.api_key == "sk-x-test"


def test_llm_security_contract_holds_with_retries(monkeypatch, llm_env):
    """Phase 8 contract: provider errors stay generic and keys never leak."""
    llm_env(LLM_PROVIDER="openrouter", OPENROUTER_API_KEY="sk-not-a-real-key")

    class _FakeFailingClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            raise httpx.ConnectError(
                "connect failed https://api.x.ai/v1/chat/completions with key sk-leak-test"
            )

    monkeypatch.setattr("app.services.ai.llm.httpx.Client", lambda *a, **k: _FakeFailingClient())
    with pytest.raises(LLMError) as excinfo:
        LLMClient(model_role="fast").chat("sys", "user")
    assert str(excinfo.value) == "LLM request failed"
    assert "api.x.ai" not in str(excinfo.value)
    assert "sk-leak-test" not in str(excinfo.value)


# ---------------------------------------------------------------------------
# L. Action routing
# ---------------------------------------------------------------------------


def test_explain_routes_to_fast(monkeypatch, llm_env):
    from app.services.actions import executor

    llm_env(LLM_PROVIDER="openrouter", OPENROUTER_API_KEY="sk-or-test")
    roles: list[str] = []

    class _FakeLLM:
        available = True

        def __init__(self, *args, **kwargs):
            roles.append(kwargs.get("model_role"))

        def chat_json(self, system, user, max_tokens=8192):
            return {"overview": "ok", "highlights": [], "risks": [], "next_steps": []}

    monkeypatch.setattr(executor, "LLMClient", _FakeLLM)
    result = executor.explain_project(types.SimpleNamespace(id=1), {}, {}, None)
    assert result.status == "success"
    assert roles == ["fast"]


def test_analyze_routes_to_reasoning_secondary(monkeypatch, llm_env):
    from app.services.actions import executor

    llm_env(LLM_PROVIDER="openrouter", OPENROUTER_API_KEY="sk-or-test")
    roles: list[str] = []

    class _FakeLLM:
        available = True

        def __init__(self, *args, **kwargs):
            roles.append(kwargs.get("model_role"))

        def chat_json(self, system, user, max_tokens=8192):
            return {"summary": "ok"}

    monkeypatch.setattr(executor, "LLMClient", _FakeLLM)
    result = executor.security_audit(types.SimpleNamespace(id=1), {}, {}, None)
    assert result.status == "success"
    assert roles == ["reasoning_secondary"]


# ---------------------------------------------------------------------------
# M. JSON compatibility (existing monkeypatch contract)
# ---------------------------------------------------------------------------


def test_chat_json_monkeypatch_contract_preserved(monkeypatch, llm_env):
    """Existing tests monkeypatch chat_json with (self, system, user, max_tokens=8192)."""
    llm_env(LLM_PROVIDER="openrouter", OPENROUTER_API_KEY="sk-or-test")
    client = LLMClient(model_role="fast")
    monkeypatch.setattr(LLMClient, "available", property(lambda self: True))

    def _fake_chat_json(self, system, user, max_tokens=8192):
        return {"overview": "LLM overview"}

    monkeypatch.setattr(LLMClient, "chat_json", _fake_chat_json)
    assert client.chat_json("sys", "user") == {"overview": "LLM overview"}


def test_explicit_constructor_kwargs_backward_compat():
    """test_llm_security style construction (api_key/base_url/model) must work."""
    client = LLMClient(
        api_key="sk-not-a-real-key",
        base_url="https://api.x.ai/v1",
        model="grok-test",
    )
    assert client.api_key == "sk-not-a-real-key"
    assert client.base_url == "https://api.x.ai/v1"
    assert client.model == "grok-test"


# ---------------------------------------------------------------------------
# N. Phase 13C regression tests
# ---------------------------------------------------------------------------


def test_empty_model_response_triggers_fallback(monkeypatch, llm_env):
    llm_env(LLM_PROVIDER="openrouter", OPENROUTER_API_KEY="sk-or-test", FAST_MODEL="nano")
    fake = _ScriptedClient(
        [
            {"status": 200, "payload": {"choices": [{"message": {"content": ""}}]}},
            {"status": 200, "payload": {"choices": [{"message": {"content": "ok"}}]}},
        ]
    )
    _patch_transport(monkeypatch, fake)
    result = LLMClient(model_role="fast").chat("sys", "user")
    assert result == "ok"


def test_whitespace_only_response_triggers_fallback(monkeypatch, llm_env):
    llm_env(LLM_PROVIDER="openrouter", OPENROUTER_API_KEY="sk-or-test", FAST_MODEL="nano")
    fake = _ScriptedClient(
        [
            {"status": 200, "payload": {"choices": [{"message": {"content": "   \n  \t  "}}]}},
            {"status": 200, "payload": {"choices": [{"message": {"content": "ok"}}]}},
        ]
    )
    _patch_transport(monkeypatch, fake)
    result = LLMClient(model_role="fast").chat("sys", "user")
    assert result == "ok"


def test_missing_choices_triggers_fallback(monkeypatch, llm_env):
    llm_env(LLM_PROVIDER="openrouter", OPENROUTER_API_KEY="sk-or-test", FAST_MODEL="nano")
    fake = _ScriptedClient(
        [
            {"status": 200, "payload": {"error": "no choices"}},
            {"status": 200, "payload": {"choices": [{"message": {"content": "ok"}}]}},
        ]
    )
    _patch_transport(monkeypatch, fake)
    result = LLMClient(model_role="fast").chat("sys", "user")
    assert result == "ok"


def test_project_name_aliases_to_name(llm_env):
    llm_env(LLM_PROVIDER="openrouter", OPENROUTER_API_KEY="", OPENAI_API_KEY="")

    payload = dict(PROJECT_PAYLOAD)
    del payload["name"]
    payload["project_name"] = "Hospital Management System"
    blueprint, provider = run_pipeline(payload)
    assert provider == "template"
    assert blueprint["metadata"]["domain_context"]["project_name"] == "Hospital Management System"


def test_name_still_works_unchanged(llm_env):
    llm_env(LLM_PROVIDER="openrouter", OPENROUTER_API_KEY="", OPENAI_API_KEY="")

    blueprint, provider = run_pipeline(dict(PROJECT_PAYLOAD))
    assert provider == "template"
    assert blueprint["metadata"]["domain_context"]["project_name"] == "Hospital Management System"


def test_super_model_is_default_reasoning_primary():
    assert OPENROUTER_ROLE_MODELS["reasoning_primary"] == "nvidia/nemotron-3-super-120b-a12b:free"
    assert OPENROUTER_ROLE_MODELS["reasoning_secondary"] == "nvidia/nemotron-3-super-120b-a12b:free"
    assert OPENROUTER_ROLE_FALLBACKS["reasoning_primary"] == ["nvidia/nemotron-3-nano-30b-a3b:free"]
