import logging
import secrets
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Provider presets: set LLM_PROVIDER=grok to use the xAI API without
# configuring OPENAI_BASE_URL / OPENAI_MODEL manually. LLM_PROVIDER=openrouter
# selects the OpenAI-compatible OpenRouter API (one key, many models).
LLM_PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-5.5"},
    "grok": {"base_url": "https://api.x.ai/v1", "model": "grok-4.5"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "model": ""},
}

# OpenRouter free-tier model defaults per agent role. These are configuration
# defaults only — every value can be overridden with the *_MODEL and
# *_FALLBACK_MODELS environment variables. Free model availability and rate
# limits change over time; the deterministic engine remains the final fallback.
OPENROUTER_ROLE_MODELS: dict[str, str] = {
    "reasoning_primary": "nvidia/nemotron-3-super-120b-a12b:free",
    "reasoning_secondary": "nvidia/nemotron-3-super-120b-a12b:free",
    "coding": "poolside/laguna-s-2.1:free",
    "fast": "nvidia/nemotron-3-nano-30b-a3b:free",
}

OPENROUTER_ROLE_FALLBACKS: dict[str, list[str]] = {
    "reasoning_primary": [
        "nvidia/nemotron-3-nano-30b-a3b:free",
    ],
    "reasoning_secondary": [
        "nvidia/nemotron-3-ultra-550b-a55b:free",
        "nvidia/nemotron-3-nano-30b-a3b:free",
    ],
    "coding": [
        "nvidia/nemotron-3-super-120b-a12b:free",
        "nvidia/nemotron-3-nano-30b-a3b:free",
    ],
    "fast": ["nvidia/nemotron-3-super-120b-a12b:free"],
}

#: Settings field holding the primary model for each agent role.
MODEL_ROLE_FIELDS: dict[str, str] = {
    "reasoning_primary": "REASONING_PRIMARY_MODEL",
    "reasoning_secondary": "REASONING_SECONDARY_MODEL",
    "coding": "CODING_MODEL",
    "fast": "FAST_MODEL",
}

#: Settings field holding the ordered fallback chain (comma-separated) for
#: each agent role.
MODEL_ROLE_FALLBACK_FIELDS: dict[str, str] = {
    "reasoning_primary": "REASONING_PRIMARY_FALLBACK_MODELS",
    "reasoning_secondary": "REASONING_SECONDARY_FALLBACK_MODELS",
    "coding": "CODING_FALLBACK_MODELS",
    "fast": "FAST_FALLBACK_MODELS",
}

_PLACEHOLDER_KEYS = {
    "sk-your-key-here",
    "xai-your-key-here",
    "sk-or-your-key-here",
    "your-api-key",
}

# Known weak / placeholder values that must never be accepted in production.
_WEAK_SECRET_KEYS = {
    "",
    "change-me-to-a-long-random-string",
    "change-me",
    "changeme",
    "your-secret-key",
    "secret",
    "supersecret",
    "insecure-secret-key",
}

MIN_SECRET_KEY_LENGTH = 32


class Settings(BaseSettings):
    """Application configuration loaded from environment / .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App -------------------------------------------------------
    APP_NAME: str = "AI Project Builder Agent"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False
    # Local dev server port. Override per-project to avoid clashes, e.g.
    # BACKEND_PORT=8021 in your .env. (Dockerfile defaults to 8000.)
    BACKEND_PORT: int = 8010

    # --- Database --------------------------------------------------
    DATABASE_URL: str = "sqlite:///./data/app.db"

    # --- Security --------------------------------------------------
    # Required in production: a random secret of at least 32 characters.
    # A known weak value or a missing value refuses to start unless DEBUG=true,
    # in which case a random development secret is generated for this process.
    SECRET_KEY: str | None = None
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    TOKEN_ALGORITHM: str = "HS256"

    # --- CORS ------------------------------------------------------
    # Development defaults: local frontends only. Production must configure
    # explicit origins and never use "*" while credentials are in use.
    CORS_ORIGINS: str = "http://localhost:3010,http://localhost:3011"

    # --- Rate limiting (auth abuse controls) ------------------------
    # DB-backed fixed-window limits, safe with multiple worker processes.
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_LOGIN: int = 10
    RATE_LIMIT_LOGIN_WINDOW: int = 900
    RATE_LIMIT_REGISTER: int = 5
    RATE_LIMIT_REGISTER_WINDOW: int = 3600
    RATE_LIMIT_FORGOT: int = 5
    RATE_LIMIT_FORGOT_WINDOW: int = 900
    RATE_LIMIT_FORGOT_IP: int = 20
    RATE_LIMIT_RESET: int = 5
    RATE_LIMIT_RESET_WINDOW: int = 900

    # --- Request body limits ----------------------------------------
    MAX_REQUEST_BODY_BYTES: int = 2_000_000

    # --- SMTP (forgot password email) ------------------------------
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "AI Project Builder <no-reply@example.com>"
    APP_PUBLIC_URL: str = "http://localhost:3010"

    # --- AI --------------------------------------------------------
    # LLM_PROVIDER selects a preset: "openai" (default), "grok" or "openrouter".
    # OPENAI_BASE_URL / OPENAI_MODEL override the preset when set.
    LLM_PROVIDER: str = "openai"
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str | None = None
    OPENAI_MODEL: str | None = None
    LLM_TEMPERATURE: float = 0.3
    LLM_TIMEOUT_SECONDS: int = 120

    # --- OpenRouter multi-model routing ----------------------------
    # One OpenRouter API key drives all four agent roles. The key is backend-
    # only: it never leaves the server and is never exposed to the frontend.
    # Each role's primary model defaults to the OpenRouter free tier when
    # LLM_PROVIDER=openrouter; the *_FALLBACK_MODELS variables (comma-
    # separated model list) extend the fallback chain. All are optional.
    OPENROUTER_API_KEY: str = ""
    REASONING_PRIMARY_MODEL: str = ""
    REASONING_SECONDARY_MODEL: str = ""
    CODING_MODEL: str = ""
    FAST_MODEL: str = ""
    REASONING_PRIMARY_FALLBACK_MODELS: str = ""
    REASONING_SECONDARY_FALLBACK_MODELS: str = ""
    CODING_FALLBACK_MODELS: str = ""
    FAST_FALLBACK_MODELS: str = ""

    # --- ChromaDB memory -------------------------------------------
    CHROMA_ENABLED: bool = False
    CHROMA_PATH: str = "./data/chroma"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def effective_api_key(self) -> str:
        """API key for the active provider.

        OpenRouter prefers its own dedicated key but stays backward
        compatible with the existing OPENAI_API_KEY when it is unset.
        """
        provider = (self.LLM_PROVIDER or "").strip().lower()
        if provider == "openrouter":
            return (self.OPENROUTER_API_KEY or "").strip() or (self.OPENAI_API_KEY or "").strip()
        return (self.OPENAI_API_KEY or "").strip()

    @property
    def llm_configured(self) -> bool:
        key = self.effective_api_key
        return bool(key) and key not in _PLACEHOLDER_KEYS

    def role_model(self, role: str) -> str:
        """Primary model for an agent role.

        Environment override wins; otherwise the OpenRouter free-tier
        default applies when the active provider is openrouter. Returns an
        empty string when the role has no configured model.
        """
        value = (getattr(self, MODEL_ROLE_FIELDS[role], "") or "").strip()
        if value:
            return value
        if (self.LLM_PROVIDER or "").strip().lower() == "openrouter":
            return OPENROUTER_ROLE_MODELS.get(role, "")
        return ""

    def role_fallback_models(self, role: str) -> list[str]:
        """Ordered fallback chain for an agent role.

        Environment override (comma-separated) wins; otherwise the
        OpenRouter free-tier default chain applies when the active provider
        is openrouter.
        """
        raw = (getattr(self, MODEL_ROLE_FALLBACK_FIELDS[role], "") or "").strip()
        chain = [m.strip() for m in raw.split(",") if m.strip()]
        if chain:
            return chain
        if (self.LLM_PROVIDER or "").strip().lower() == "openrouter":
            return OPENROUTER_ROLE_FALLBACKS.get(role, [])
        return []

    @model_validator(mode="after")
    def _validate_cors_origins(self) -> "Settings":
        """Production fails fast on permissive or unset CORS origins.

        Credentials (Authorization bearer tokens) are always used, so "*" is
        never acceptable. In production the dev localhost default is not
        enough either: the operator must list the real frontend origins.
        """
        origins = self.cors_origin_list
        dev_default = {"http://localhost:3010", "http://localhost:3011"}
        if "*" in origins:
            raise ValueError(
                "CORS_ORIGINS must not contain '*' because the API uses "
                "credentialed requests (Bearer tokens). List explicit origins."
            )
        for origin in origins:
            if not (origin.startswith("http://") or origin.startswith("https://")):
                raise ValueError(
                    f"CORS origin '{origin}' is not a valid http(s) origin."
                )
        if self.DEBUG:
            return self
        if set(origins) == dev_default or not origins:
            raise ValueError(
                "CORS_ORIGINS must be explicitly configured in production. "
                "The development localhost default is not acceptable: set the "
                "real frontend origin(s), e.g. "
                "CORS_ORIGINS=https://app.example.com,https://admin.example.com"
            )
        return self

    @model_validator(mode="after")
    def _validate_secret_key(self) -> "Settings":
        secret = (self.SECRET_KEY or "").strip()
        if secret and secret not in _WEAK_SECRET_KEYS and len(secret) >= MIN_SECRET_KEY_LENGTH:
            return self
        if self.DEBUG:
            # Development convenience only: generate a random per-process key.
            # Never generates a secret in non-DEBUG (production) mode.
            self.SECRET_KEY = secrets.token_hex(32)
            logger.warning(
                "SECRET_KEY is not configured with a strong value; generated a random "
                "development key for this process (sessions reset on restart). "
                "Set SECRET_KEY in .env to keep it stable. DEVELOPMENT ONLY."
            )
            return self
        raise ValueError(
            "SECRET_KEY is not configured with a strong value and production mode "
            "refuses to start without one. Generate a random secret of at least 32 "
            'characters (e.g. python -c "import secrets; print(secrets.token_hex(32))") '
            "and set it via SECRET_KEY in .env or the environment."
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
