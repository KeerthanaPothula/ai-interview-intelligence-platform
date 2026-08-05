"""Tests for app.services.gemini_service — rate-limit and error propagation.

These exercise generate_questions()/generate_text() end-to-end against a
fake Gemini client, confirming the retry + 429 status/message behavior
implemented in app.core.ai_reliability actually reaches callers through
this service, not just the shared helper in isolation.
"""

from __future__ import annotations

import pytest
from google.genai import errors as genai_errors

from app.core import ai_reliability
from app.core.exceptions import AIServiceError
from app.services import gemini_service


class _FastSettings:
    """Minimal settings stand-in with near-zero retry delay for fast tests."""

    GEMINI_MAX_RETRIES = 3
    GEMINI_RETRY_BACKOFF_SECONDS = 0.001
    GEMINI_MODEL = "gemini-test-model"


@pytest.fixture(autouse=True)
def _fast_retry_settings(monkeypatch):
    monkeypatch.setattr(ai_reliability, "get_settings", lambda: _FastSettings())
    monkeypatch.setattr(gemini_service, "get_settings", lambda: _FastSettings())


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeModels:
    def __init__(self, fn) -> None:
        self._fn = fn

    def generate_content(self, *, model, contents):
        return self._fn()


class _FakeClient:
    def __init__(self, fn) -> None:
        self.models = _FakeModels(fn)


def _patch_client(monkeypatch, fn):
    monkeypatch.setattr(gemini_service, "_get_client", lambda: _FakeClient(fn))


VALID_QUESTIONS_JSON = (
    '[{"body": "Tell me about a challenging project.", "category": "behavioral"}, '
    '{"body": "How would you design a URL shortener?", "category": "technical"}]'
)


class TestGenerateQuestionsRateLimiting:
    def test_persistent_rate_limit_raises_429_with_standard_message(self, monkeypatch):
        def always_rate_limited():
            raise genai_errors.APIError(429, {"error": {"message": "rate limited"}})

        _patch_client(monkeypatch, always_rate_limited)

        with pytest.raises(AIServiceError) as exc_info:
            gemini_service.generate_questions(
                job_role="Backend Engineer",
                job_description="Build APIs.",
                count=2,
            )

        assert exc_info.value.status_code == 429
        assert exc_info.value.detail == ai_reliability.RATE_LIMIT_MESSAGE

    def test_transient_rate_limit_recovers_and_returns_questions(self, monkeypatch):
        attempts = {"n": 0}

        def flaky():
            attempts["n"] += 1
            if attempts["n"] < 2:
                raise genai_errors.APIError(429, {"error": {"message": "rate limited"}})
            return _FakeResponse(VALID_QUESTIONS_JSON)

        _patch_client(monkeypatch, flaky)

        questions = gemini_service.generate_questions(
            job_role="Backend Engineer",
            job_description="Build APIs.",
            count=2,
        )

        assert len(questions) == 2
        assert attempts["n"] == 2

    def test_invalid_api_key_fails_fast_without_retry(self, monkeypatch):
        attempts = {"n": 0}

        def invalid_key():
            attempts["n"] += 1
            raise genai_errors.APIError(401, {"error": {"message": "invalid key"}})

        _patch_client(monkeypatch, invalid_key)

        with pytest.raises(AIServiceError) as exc_info:
            gemini_service.generate_questions(
                job_role="Backend Engineer",
                job_description="Build APIs.",
                count=2,
            )

        assert attempts["n"] == 1
        assert exc_info.value.status_code != 429


class TestGenerateTextRateLimiting:
    """generate_text() is used by resume analysis, which is designed to
    fail open (regex-based fallback) rather than surface an HTTP error —
    it must keep raising RuntimeError, not AIServiceError, even though it
    now goes through the same retry/429 machinery internally."""

    def test_persistent_rate_limit_raises_runtime_error_not_ai_service_error(
        self, monkeypatch
    ):
        def always_rate_limited():
            raise genai_errors.APIError(429, {"error": {"message": "rate limited"}})

        _patch_client(monkeypatch, always_rate_limited)

        with pytest.raises(RuntimeError):
            gemini_service.generate_text("some prompt")

    def test_transient_rate_limit_recovers(self, monkeypatch):
        attempts = {"n": 0}

        def flaky():
            attempts["n"] += 1
            if attempts["n"] < 2:
                raise genai_errors.APIError(429, {"error": {"message": "rate limited"}})
            return _FakeResponse("plain text result")

        _patch_client(monkeypatch, flaky)

        result = gemini_service.generate_text("some prompt")
        assert result == "plain text result"
