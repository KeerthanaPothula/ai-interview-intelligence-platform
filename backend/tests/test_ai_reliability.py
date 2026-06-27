"""Tests for app.core.ai_reliability — retry/backoff and safe JSON parsing."""

from __future__ import annotations

import httpx
import pytest
from google.genai import errors as genai_errors

from app.core import ai_reliability
from app.core.exceptions import AIServiceError


class _FastSettings:
    """Minimal settings stand-in with near-zero retry delay for fast tests."""

    GEMINI_MAX_RETRIES = 3
    GEMINI_RETRY_BACKOFF_SECONDS = 0.001


@pytest.fixture(autouse=True)
def _fast_retry_settings(monkeypatch):
    monkeypatch.setattr(ai_reliability, "get_settings", lambda: _FastSettings())


# ---------------------------------------------------------------------------
# call_gemini_with_retry
# ---------------------------------------------------------------------------


def test_call_gemini_with_retry_succeeds_first_try():
    result = ai_reliability.call_gemini_with_retry(lambda: "ok", operation="test op")
    assert result == "ok"


def test_call_gemini_with_retry_recovers_after_timeout():
    attempts = {"n": 0}

    def flaky():
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise httpx.TimeoutException("slow")
        return "recovered"

    result = ai_reliability.call_gemini_with_retry(flaky, operation="test op")
    assert result == "recovered"
    assert attempts["n"] == 2


def test_call_gemini_with_retry_recovers_after_rate_limit():
    attempts = {"n": 0}

    def flaky():
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise genai_errors.APIError(429, {"error": {"message": "rate limited"}})
        return "recovered"

    result = ai_reliability.call_gemini_with_retry(flaky, operation="test op")
    assert result == "recovered"


def test_call_gemini_with_retry_exhausts_retries_on_persistent_timeout():
    def always_times_out():
        raise httpx.TimeoutException("too slow")

    with pytest.raises(AIServiceError) as exc_info:
        ai_reliability.call_gemini_with_retry(always_times_out, operation="test op")
    assert exc_info.value.status_code == 502


def test_call_gemini_with_retry_does_not_retry_non_retryable_error():
    attempts = {"n": 0}

    def bad_request():
        attempts["n"] += 1
        raise genai_errors.APIError(400, {"error": {"message": "bad request"}})

    with pytest.raises(AIServiceError):
        ai_reliability.call_gemini_with_retry(bad_request, operation="test op")
    assert attempts["n"] == 1


# ---------------------------------------------------------------------------
# parse_json_response
# ---------------------------------------------------------------------------


def test_parse_json_response_plain_object():
    result = ai_reliability.parse_json_response(
        '{"a": 1}', operation="test op", expect=dict
    )
    assert result == {"a": 1}


def test_parse_json_response_strips_markdown_fences():
    raw = '```json\n{"a": 1}\n```'
    result = ai_reliability.parse_json_response(raw, operation="test op", expect=dict)
    assert result == {"a": 1}


def test_parse_json_response_repairs_surrounding_commentary():
    raw = 'Sure, here is the JSON:\n{"a": 1}\nLet me know if you need anything else.'
    result = ai_reliability.parse_json_response(raw, operation="test op", expect=dict)
    assert result == {"a": 1}


def test_parse_json_response_parses_array():
    result = ai_reliability.parse_json_response(
        '[{"a": 1}, {"a": 2}]', operation="test op", expect=list
    )
    assert result == [{"a": 1}, {"a": 2}]


def test_parse_json_response_raises_on_unparseable_text():
    with pytest.raises(AIServiceError) as exc_info:
        ai_reliability.parse_json_response(
            "not json at all", operation="test op", expect=dict
        )
    assert exc_info.value.status_code == 502


def test_parse_json_response_raises_on_wrong_top_level_type():
    with pytest.raises(AIServiceError):
        ai_reliability.parse_json_response('{"a": 1}', operation="test op", expect=list)
