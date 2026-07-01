from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Typed application settings.

    pydantic-settings resolves values in this priority order:
      1. Real environment variables (set by the OS or docker-compose env_file)
      2. Variables found in the .env file on disk
      3. Field defaults defined below

    This means docker-compose always wins over .env, and .env wins
    over defaults — which is the behaviour you want in every environment.
    """

    model_config = SettingsConfigDict(
        # Search for .env in the process CWD (backend/) first, then the
        # repo root (../). This lets developers run `cp .env.example .env`
        # once at the repo root and have both Alembic (from backend/) and
        # uvicorn pick it up without needing a separate backend/.env copy.
        # Inside Docker, docker-compose injects vars as real env vars via
        # `env_file: .env`, so neither file is read there.
        env_file=[".env", "../.env"],
        env_file_encoding="utf-8",
        # Map env vars to fields case-insensitively:
        # DATABASE_URL → database_url, ENVIRONMENT → environment, etc.
        case_sensitive=False,
        # Silently ignore any extra env vars present in the environment
        # (e.g. shell variables, Docker injected vars) that have no
        # matching field. Without this, pydantic raises a validation error.
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------

    # Controls runtime behaviour such as error detail level and OpenAPI
    # availability. Constrained to two valid values — any other value
    # raises a validation error at startup rather than silently misbehaving.
    ENVIRONMENT: Literal["development", "production"] = "development"

    # When True, FastAPI surfaces full tracebacks in 500 responses and
    # enables /docs and /redoc. Must be False in production.
    DEBUG: bool = True

    # ------------------------------------------------------------------
    # Database
    # No default — the app refuses to start if DATABASE_URL is absent
    # or empty, which is the safest possible failure mode.
    # ------------------------------------------------------------------

    DATABASE_URL: str = Field(..., min_length=1)

    # ------------------------------------------------------------------
    # JWT Authentication
    # ------------------------------------------------------------------

    # HMAC signing secret. min_length=32 enforces a minimum entropy floor
    # at startup rather than at the first token operation.
    # No default — forces the developer to set an explicit value.
    JWT_SECRET_KEY: str = Field(..., min_length=32)

    # Signing algorithm. Validated below against the supported set so
    # a typo (e.g. "hs256") raises a clear error instead of silent failure.
    JWT_ALGORITHM: str = "HS256"

    # Token lifetime in minutes. gt=0 rejects zero or negative values
    # using Pydantic's built-in numeric constraint — no custom validator needed.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=1440, gt=0)

    # ------------------------------------------------------------------
    # Gemini API  (consumed from Week 2 onward)
    # Declared here so every service imports from config rather than
    # calling os.environ directly — a single source of truth.
    # ------------------------------------------------------------------

    GEMINI_API_KEY: str = Field(..., min_length=1)

    # Single source of truth for the Gemini model name used by every
    # service. Previously each service hardcoded its own "gemini-2.0-flash"
    # module constant; centralizing here means upgrading models is a
    # one-line config change instead of a multi-file find-and-replace.
    GEMINI_MODEL: str = "gemini-2.0-flash"

    # How many questions to request from Gemini per session.
    # ge=1 and le=20 enforce sensible bounds at startup.
    # The Gemini prompt receives this value directly as the requested count.
    MAX_QUESTIONS_PER_SESSION: int = Field(default=10, ge=1, le=20)

    # Maximum seconds to wait for Gemini to return a response.
    # gt=0 prevents an accidental zero that would make every request time out immediately.
    # The timeout applies to the full HTTP round-trip (connect + read).
    GEMINI_TIMEOUT_SECONDS: int = Field(default=30, gt=0)

    # Maximum number of attempts (including the first) for a Gemini call
    # before app.core.ai_reliability.call_gemini_with_retry gives up and
    # raises AIServiceError. ge=1 so retries can be disabled (1 = no retry)
    # without becoming an invalid value.
    GEMINI_MAX_RETRIES: int = Field(default=3, ge=1)

    # Base delay in seconds for exponential backoff between retries:
    # attempt N waits backoff_base * 2^(N-1) seconds. gt=0 prevents a
    # zero-delay busy-retry loop against a struggling upstream.
    GEMINI_RETRY_BACKOFF_SECONDS: float = Field(default=1.0, gt=0)

    # ------------------------------------------------------------------
    # Whisper  (consumed from Week 2 onward)
    # Validated below against the set of known model names.
    # ------------------------------------------------------------------

    WHISPER_MODEL: str = "base"

    # ------------------------------------------------------------------
    # Processing Pipeline  (Week 3 — Whisper transcription + Gemini eval)
    # ------------------------------------------------------------------

    # Master switch for the audio processing pipeline.
    # False: POST /process returns 503; upload_audio() skips BackgroundTask
    #   enqueue so tests can upload audio without triggering Whisper.
    # True (production default): both enqueue and the /process endpoint
    #   are active.
    # The test suite sets os.environ.setdefault("ENABLE_AUDIO_PROCESSING",
    # "false") in conftest.py before any app import so that this default
    # never applies during test runs.
    ENABLE_AUDIO_PROCESSING: bool = True

    # Maximum characters of transcript text sent to Gemini for evaluation.
    # Transcripts longer than this are truncated before the API call to
    # stay within Gemini's effective context window and control API cost.
    # Truncation happens in processing_service before calling evaluation_service.
    # gt=0: a zero value would truncate every transcript to empty.
    MAX_TRANSCRIPT_CHARS: int = Field(default=20000, gt=0)

    # Maximum seconds the Whisper transcription call is permitted to run.
    # The processing service enforces this by joining the transcription
    # thread with timeout=WHISPER_TIMEOUT_SECONDS; a join timeout causes
    # the job to be marked failed with a "timed out" error message.
    # gt=0: zero would immediately time out every transcription job.
    WHISPER_TIMEOUT_SECONDS: int = Field(default=300, gt=0)

    # ------------------------------------------------------------------
    # RAG (Retrieval-Augmented Generation)  — resume-personalised questions
    # ------------------------------------------------------------------

    # Word count per chunk when splitting resume/document text for embedding.
    RAG_CHUNK_SIZE: int = Field(default=200, gt=0)

    # Word overlap between consecutive chunks, to avoid losing context at
    # chunk boundaries. Must be smaller than RAG_CHUNK_SIZE or every chunk
    # would advance by zero (or a negative) word count.
    RAG_CHUNK_OVERLAP: int = Field(default=50, ge=0)

    @model_validator(mode="after")
    def rag_overlap_must_be_smaller_than_chunk_size(self) -> "Settings":
        if self.RAG_CHUNK_OVERLAP >= self.RAG_CHUNK_SIZE:
            raise ValueError("RAG_CHUNK_OVERLAP must be smaller than RAG_CHUNK_SIZE.")
        return self

    # ------------------------------------------------------------------
    # File Uploads  (consumed from Week 2 onward)
    # ------------------------------------------------------------------

    # Relative or absolute path to the audio upload directory.
    # Created automatically on first upload by upload_service — must not
    # be validated for existence here because Docker volumes are mounted
    # after the Python process starts.
    UPLOAD_DIR: str = Field(default="uploads", min_length=1)

    # Ceiling for accepted audio files in megabytes.
    # upload_service converts this to bytes: MB × 1024 × 1024.
    # gt=0 prevents accidental zero that would reject every upload.
    MAX_UPLOAD_SIZE_MB: int = Field(default=10, gt=0)

    # Ceiling for accepted resume uploads (PDF/DOCX) in megabytes.
    # Resumes are plain text-bearing documents, not audio/video — a much
    # smaller cap than MAX_UPLOAD_SIZE_MB is appropriate.
    MAX_RESUME_UPLOAD_SIZE_MB: int = Field(default=5, gt=0)

    # ------------------------------------------------------------------
    # CORS
    # ------------------------------------------------------------------

    # Allowed frontend origins for cross-origin requests, as a
    # comma-separated string in the environment (e.g.
    # "http://localhost:3000,http://localhost:5173"), parsed into a list
    # below. Defaults to an empty list — no origins are allowed and
    # credentialed CORS is disabled (see main.py) until this is configured.
    #
    # Declared as `str | list[str]` rather than `list[str]` because
    # pydantic-settings attempts to JSON-decode env values for fields typed
    # as `list[str]`, which fails for a plain comma-separated string before
    # parse_cors_origins below ever runs. Allowing `str` in the type lets
    # pydantic-settings pass the raw string through to the validator.
    CORS_ORIGINS: str | list[str] = []

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @model_validator(mode="after")
    def apply_dev_cors_default(self) -> "Settings":
        # In development, if CORS_ORIGINS was never set (empty list), default
        # to both common Vite/CRA dev-server ports so the app works out-of-the-
        # box after a plain `cp .env.example .env` without editing CORS_ORIGINS.
        # Production deployments must set CORS_ORIGINS explicitly.
        if self.ENVIRONMENT == "development" and not self.CORS_ORIGINS:
            self.CORS_ORIGINS = ["http://localhost:5173", "http://localhost:3000"]
        return self

    # ------------------------------------------------------------------
    # Validators
    # field_validator runs after the field's own type coercion,
    # so `v` is already the correct Python type when it arrives here.
    # ------------------------------------------------------------------

    @field_validator("JWT_ALGORITHM")
    @classmethod
    def validate_jwt_algorithm(cls, v: str) -> str:
        supported = {"HS256", "HS384", "HS512"}
        if v not in supported:
            raise ValueError(
                f"JWT_ALGORITHM '{v}' is not supported. "
                f"Choose one of: {sorted(supported)}"
            )
        return v

    @field_validator("WHISPER_MODEL")
    @classmethod
    def validate_whisper_model(cls, v: str) -> str:
        valid = {"tiny", "base", "small", "medium", "large-v2", "large-v3"}
        if v not in valid:
            raise ValueError(
                f"WHISPER_MODEL '{v}' is not a recognised Whisper checkpoint. "
                f"Choose one of: {sorted(valid)}"
            )
        return v

    # mode="after" runs once all individual fields have been validated
    # and coerced, so both ENVIRONMENT and DEBUG are guaranteed to be
    # their final Python types when this check executes.
    @model_validator(mode="after")
    def production_must_not_have_debug_enabled(self) -> "Settings":
        if self.ENVIRONMENT == "production" and self.DEBUG:
            raise ValueError(
                "DEBUG=true is not permitted when ENVIRONMENT=production. "
                "Set DEBUG=false before deploying."
            )
        return self

    # ------------------------------------------------------------------
    # Phase 3 — Login rate limiting & account lockout
    #
    # The limiter (app/core/rate_limit.py) is an in-memory, single-process
    # fixed-window counter. It is deliberately not Redis-backed: this
    # project has no Redis infrastructure configured anywhere, and adding
    # one purely for rate limiting would be a disproportionate
    # architecture change for a single-worker deployment. Known
    # limitation: state does not survive a process restart and is not
    # shared across multiple Uvicorn/Gunicorn workers — see SECURITY.md.
    # ------------------------------------------------------------------

    # Maximum login attempts permitted from a single client IP within
    # RATE_LIMIT_LOGIN_WINDOW_SECONDS before further attempts are
    # rejected with HTTP 429. Applies regardless of which email is used,
    # so it also throttles email-enumeration attempts across accounts.
    RATE_LIMIT_LOGIN_ATTEMPTS: int = Field(default=5, ge=1)

    # Width of the fixed window (seconds) used by RATE_LIMIT_LOGIN_ATTEMPTS.
    RATE_LIMIT_LOGIN_WINDOW_SECONDS: int = Field(default=60, gt=0)

    # Number of consecutive failed password attempts against one account
    # before that account is temporarily locked, independent of the
    # IP-based limiter above.
    ACCOUNT_LOCKOUT_THRESHOLD: int = Field(default=5, ge=1)

    # Base lockout duration in minutes. Each successive lockout for the
    # same account doubles this value (progressive backoff), capped at
    # ACCOUNT_LOCKOUT_MAX_DURATION_MINUTES.
    ACCOUNT_LOCKOUT_DURATION_MINUTES: int = Field(default=15, gt=0)

    # Ceiling on the progressive lockout duration so a repeatedly
    # targeted account is never locked indefinitely by the doubling
    # formula.
    ACCOUNT_LOCKOUT_MAX_DURATION_MINUTES: int = Field(default=1440, gt=0)

    # ------------------------------------------------------------------
    # Phase 3 — Refresh tokens
    # ------------------------------------------------------------------

    # Refresh token lifetime in days. Refresh tokens are long-lived
    # compared to access tokens and are stored hashed in the
    # refresh_tokens table so individual tokens can be revoked.
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=30, gt=0)

    # ------------------------------------------------------------------
    # Phase 3 — Security headers middleware
    # Environment-aware: HSTS is meaningless (and actively harmful) over
    # plain HTTP in local development, so SecurityHeadersMiddleware only
    # emits Strict-Transport-Security when ENVIRONMENT == "production".
    # ------------------------------------------------------------------

    # Content-Security-Policy header value. Default is restrictive
    # (same-origin only); override per-deployment if the API ever serves
    # browser-rendered content directly (it currently does not — this is
    # primarily a defense-in-depth header for an API-only backend).
    CSP_POLICY: str = "default-src 'self'; frame-ancestors 'none'"

    # max-age for Strict-Transport-Security, in seconds. Only sent when
    # ENVIRONMENT == "production" (see SecurityHeadersMiddleware).
    HSTS_MAX_AGE_SECONDS: int = Field(default=31536000, gt=0)

    # Permissions-Policy header value. Disables browser features this API
    # never needs.
    PERMISSIONS_POLICY: str = "geolocation=(), microphone=(), camera=(), payment=()"

    # ------------------------------------------------------------------
    # Phase 4 — Logging
    # ------------------------------------------------------------------

    # Root logger level. Validated below against Python's standard level
    # names so a typo (e.g. "INF0") fails fast at startup.
    LOG_LEVEL: str = "INFO"

    # "json" emits one JSON object per line (machine-parseable, suitable for
    # log aggregation in production). "text" emits the original
    # human-readable line format, more convenient for local terminals.
    LOG_FORMAT: Literal["json", "text"] = "json"

    # Header name used to read an inbound correlation ID and to echo it
    # back on the response. A client-supplied value is honoured so a
    # request can be correlated end-to-end across services; if absent, a
    # new ID is generated.
    REQUEST_ID_HEADER: str = "X-Request-ID"

    # Requests slower than this are logged at WARNING with their timing,
    # independently of whether they succeeded, to surface latency issues
    # that wouldn't otherwise show up as errors.
    SLOW_REQUEST_THRESHOLD_MS: int = Field(default=1000, gt=0)

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(
                f"LOG_LEVEL '{v}' is not a recognised logging level. "
                f"Choose one of: {sorted(valid)}"
            )
        return upper

    # ------------------------------------------------------------------
    # Phase 4 — Metrics
    # ------------------------------------------------------------------

    # Master switch for Prometheus instrumentation and the /metrics
    # endpoint. Disabling this removes the metrics middleware overhead
    # entirely rather than just hiding the endpoint.
    ENABLE_METRICS: bool = True

    # ------------------------------------------------------------------
    # Phase 4 — OpenTelemetry tracing
    # Disabled by default: tracing pulls in the opentelemetry SDK and, if
    # misconfigured, can add latency. Deployments opt in explicitly.
    # ------------------------------------------------------------------

    ENABLE_TRACING: bool = False

    # Logical service name attached to every span (the "service.name"
    # resource attribute), used to distinguish this service from others
    # in a shared tracing backend.
    OTEL_SERVICE_NAME: str = "ai-interview-intelligence-platform"

    # OTLP/HTTP collector endpoint (e.g. "http://localhost:4318/v1/traces").
    # When ENABLE_TRACING is True but this is unset, spans are exported to
    # the console instead — useful for local debugging without standing up
    # a collector.
    OTEL_EXPORTER_OTLP_ENDPOINT: str | None = None

    # Fraction of traces to sample, from 0.0 (none) to 1.0 (all). Lower
    # this in high-traffic production deployments to control exporter
    # volume and cost.
    OTEL_TRACES_SAMPLE_RATE: float = Field(default=1.0, ge=0.0, le=1.0)

    # ------------------------------------------------------------------
    # Phase 4 — Health & readiness
    # ------------------------------------------------------------------

    # Maximum seconds the /ready endpoint waits for its database
    # connectivity check before reporting that dependency as down. Kept
    # short and strict because a slow readiness probe delays orchestrators
    # detecting a genuinely unready instance.
    READINESS_DB_TIMEOUT_SECONDS: float = Field(default=2.0, gt=0)


@lru_cache
def get_settings() -> Settings:
    """
    Return the application-wide Settings singleton.

    @lru_cache constructs Settings() exactly once per interpreter process.
    Every subsequent call returns the same cached object — no repeated
    .env file reads or environment variable lookups.

    How to use:

      # In module-level code or services:
      from app.config import get_settings
      settings = get_settings()

      # As a FastAPI dependency (enables override in tests):
      from fastapi import Depends
      def my_route(settings: Settings = Depends(get_settings)):
          ...

    To override settings in tests:
      app.dependency_overrides[get_settings] = lambda: Settings(
          DATABASE_URL="postgresql+psycopg2://...",
          ...
      )
    """
    return Settings()
