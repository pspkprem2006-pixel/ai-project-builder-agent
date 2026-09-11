"""Configurable OpenAI-compatible LLM client.

Works with any Chat Completions API (OpenAI, Azure OpenAI, Ollama,
LM Studio, local vLLM, OpenRouter, etc.) by overriding OPENAI_BASE_URL.

Model resolution precedence (documented contract):
    1. explicit ``model`` argument
    2. ``model_role`` argument  (role model, then role fallback chain)
    3. provider default model   (OPENAI_MODEL, else the provider preset)

Transient provider failures (timeouts, connection errors, HTTP 429/5xx)
are retried once per model before moving to the next model in the chain.
All other failures raise ``LLMError`` immediately. Exhausting the chain
raises the same generic ``LLMError`` so callers keep their existing
deterministic fallbacks.
"""
import json
import logging
import re
from typing import Any

import httpx

from app.config import LLM_PROVIDER_PRESETS, get_settings

logger = logging.getLogger(__name__)


class LLMNotConfiguredError(Exception):
    """Raised when no API key is set and live generation was requested."""


class LLMError(Exception):
    """Raised when the LLM provider returns an unusable response."""


class _RetryableError(Exception):
    """Internal marker for transient provider failures (retried once)."""


#: Bounded client-level retry policy: 1 retry per model per transient
#: failure. The pipeline also has its own bounded fallbacks (per-section
#: semantic regeneration and the durable GenerationJob retries), so this
#: must never grow into a large loop.
MAX_ATTEMPTS_PER_MODEL = 2

#: HTTP statuses that are transient provider-side conditions.
TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}


def _extract_json(text: str) -> dict[str, Any]:
    """Extract a JSON object from a model response, tolerating fences and prose."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            data = json.loads(text[start : end + 1])
        else:
            raise
    if not isinstance(data, dict):
        raise LLMError("LLM response is not a JSON object")
    return data


class LLMClient:
    """Thin async-friendly synchronous client over Chat Completions.

    ``LLMClient()`` and ``LLMClient(model=...)`` keep their existing meaning.
    ``model_role`` selects the configured model for an agent role (with its
    fallback chain); it is ignored when an explicit ``model`` is passed.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        timeout: int | None = None,
        model_role: str | None = None,
        response_format: bool = False,
    ) -> None:
        settings = get_settings()
        self.provider = (settings.LLM_PROVIDER or "openai").strip().lower()
        preset = LLM_PROVIDER_PRESETS.get(self.provider, {})
        self.api_key = api_key or settings.effective_api_key
        self.base_url = (
            base_url or settings.OPENAI_BASE_URL or preset.get("base_url", "")
        ).rstrip("/")
        self.model_role = model_role
        self.response_format = bool(response_format)
        self.model_chain = self._resolve_model_chain(model, model_role, settings, preset)
        self.model = self.model_chain[0] if self.model_chain else ""
        self.temperature = temperature if temperature is not None else settings.LLM_TEMPERATURE
        self.timeout = timeout or settings.LLM_TIMEOUT_SECONDS

    @staticmethod
    def _resolve_model_chain(
        model: str | None,
        model_role: str | None,
        settings: Any,
        preset: dict[str, str],
    ) -> list[str]:
        """Ordered models to try: explicit model, then role, then provider default.

        Precedence (see module docstring): explicit ``model`` > ``model_role``
        > provider default model (OPENAI_MODEL, else preset). A role resolves
        to its primary model followed by its configured fallback chain.
        """
        if model:
            return [model]
        if model_role:
            primary = settings.role_model(model_role)
            if primary:
                return [primary, *settings.role_fallback_models(model_role)]
        default = settings.OPENAI_MODEL or preset.get("model", "")
        return [default] if default else []

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def chat(self, system: str, user: str, max_tokens: int = 4096) -> str:
        if not self.available:
            raise LLMNotConfiguredError("No LLM API key configured")
        last_error: Exception | None = None
        for model in self.model_chain:
            for attempt in range(1, MAX_ATTEMPTS_PER_MODEL + 1):
                try:
                    return self._post(model, system, user, max_tokens)
                except _RetryableError as exc:
                    last_error = exc
                    logger.warning(
                        "LLM provider transient failure model=%s attempt=%d/%d: %s",
                        model,
                        attempt,
                        MAX_ATTEMPTS_PER_MODEL,
                        exc,
                    )
        # Generic by design: never surface provider details to callers.
        raise LLMError("LLM request failed") from last_error

    def _post(self, model: str, system: str, user: str, max_tokens: int) -> str:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.temperature,
            "max_tokens": max_tokens,
        }
        if self.response_format:
            # Optional, opt-in only: providers without structured-output
            # support are never required to receive this field.
            payload["response_format"] = {"type": "json_object"}
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    f"{self.base_url}/chat/completions", headers=headers, json=payload
                )
                resp.raise_for_status()
                data = resp.json()
            choices = data.get("choices")
            if not choices:
                raise _RetryableError("empty model response")
            message = choices[0].get("message")
            if not message:
                raise _RetryableError("empty model response")
            content = message.get("content")
            if content is None or not content.strip():
                raise _RetryableError("empty model response")
            return content
        except httpx.TimeoutException as exc:
            raise _RetryableError("provider timed out") from exc
        except httpx.ConnectError as exc:
            raise _RetryableError("provider connection failed") from exc
        except httpx.HTTPStatusError as exc:
            # Never retry client/authentication errors (401, 400, ...) or
            # invalid-model errors; only transient server-side conditions.
            if exc.response.status_code in TRANSIENT_STATUS_CODES:
                raise _RetryableError(
                    f"provider returned HTTP {exc.response.status_code}"
                ) from exc
            # Log the provider detail server-side only; never surface it to
            # users or persist it in job error fields (provider messages can
            # echo request metadata).
            logger.error("LLM provider request failed: %s", exc)
            raise LLMError("LLM request failed") from exc
        except httpx.HTTPError as exc:
            # Log the provider detail server-side only; never surface it to
            # users or persist it in job error fields (provider messages can
            # echo request metadata).
            logger.error("LLM provider request failed: %s", exc)
            raise LLMError("LLM request failed") from exc
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            logger.error("Unexpected LLM response shape: %s", exc)
            raise LLMError("Unexpected LLM response") from exc

    def chat_json(self, system: str, user: str, max_tokens: int = 8192) -> dict[str, Any]:
        content = self.chat(system, user, max_tokens=max_tokens)
        try:
            return _extract_json(content)
        except json.JSONDecodeError as exc:
            raise LLMError("LLM did not return valid JSON") from exc
