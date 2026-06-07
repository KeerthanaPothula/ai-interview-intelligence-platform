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

    # ------------------------------------------------------------------
    # Whisper  (consumed from Week 2 onward)
    # Validated below against the set of known model names.
    # ------------------------------------------------------------------

    WHISPER_MODEL: str = "base"

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
