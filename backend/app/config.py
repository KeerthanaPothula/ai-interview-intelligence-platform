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
        # Read .env from the process working directory as a fallback.
        # Inside Docker, docker-compose already injects all variables as
        # real env vars via `env_file: .env`, so this file is not read.
        # It is only used when running the app locally without Docker.
        env_file=".env",
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

    # How many questions to request from Gemini per session.
    # ge=1 and le=20 enforce sensible bounds at startup.
    # The Gemini prompt receives this value directly as the requested count.
    MAX_QUESTIONS_PER_SESSION: int = Field(default=10, ge=1, le=20)

    # Maximum seconds to wait for Gemini to return a response.
    # gt=0 prevents an accidental zero that would make every request time out immediately.
    # The timeout applies to the full HTTP round-trip (connect + read).
    GEMINI_TIMEOUT_SECONDS: int = Field(default=30, gt=0)

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
