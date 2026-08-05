"""Shared reliability helpers for Gemini API calls.

Every service that talks to Gemini faces the same three problems: the
network call can time out or be rate-limited, the model can be slow to
respond, and the model is not guaranteed to return valid JSON even when
explicitly instructed to. This module centralizes the fix for all three so
individual services do not each reinvent (or skip) retry, timeout, and JSON
safety handling.

Usage:

    from app.core.ai_reliability import call_gemini_with_retry, parse_json_response

    response = call_gemini_with_retry(
        lambda: client.models.generate_content(model=model, contents=prompt),
        operation="session report generation",
    )
    data = parse_json_response(response.text, operation="session report generation")
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Callable, TypeVar

import httpx
from google.genai import errors as genai_errors

from app.config import get_settings
from app.core.exceptions import AIServiceError
from app.core.metrics import observe_ai_request
from app.core.tracing import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

# Matches both ```json ... ``` and ``` ... ``` — Gemini wraps JSON in markdown
# fences even when explicitly instructed not to. re.DOTALL lets the inner
# content span multiple lines.
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)

T = TypeVar("T")


# Exact, user-facing message for a Gemini rate-limit (429) that persists
# through all retries. Kept as a module-level constant so every caller and
# every test asserts against the same string rather than a copy of it.
RATE_LIMIT_MESSAGE = (
    "The AI service is temporarily rate limited. Please try again in a few minutes."
)

# Auth-related API error codes. These indicate a broken/invalid API key or
# an unauthorized project, not a transient condition — retrying cannot help
# and only burns additional quota against an already-failing key, so these
# are never retried.
_AUTH_ERROR_CODES = frozenset({401, 403})


def call_gemini_with_retry(
    fn: Callable[[], T],
    *,
    operation: str,
) -> T:
    """Call a zero-argument Gemini SDK invocation with retry + backoff.

    Retries on timeout and on retryable API errors (429 rate limit, 5xx
    server errors) using exponential backoff. Does not retry:
      - Authentication errors (401/403 — invalid/revoked API key). Retrying
        a bad key cannot succeed and only wastes quota, so these fail fast.
      - Other non-retryable APIError codes (e.g. 400 bad request), since
        retrying an invalid request will not help either.

    Raises:
        AIServiceError: after all retries are exhausted, or immediately on a
            non-retryable API error. The underlying exception is always
            logged with the full traceback (exc_info) for debugging, even
            though the raised AIServiceError carries only a generic,
            user-safe message. A persistent 429 (rate limit still exceeded
            after all retries) is raised as AIServiceError with
            status_code=429 and RATE_LIMIT_MESSAGE — every other failure
            keeps the previous generic 502 "currently unavailable" message.
    """
    settings = get_settings()
    max_retries = settings.GEMINI_MAX_RETRIES
    backoff_base = settings.GEMINI_RETRY_BACKOFF_SECONDS

    start = time.perf_counter()

    def _record(status: str) -> None:
        observe_ai_request(
            provider="gemini",
            operation=operation,
            status=status,
            duration_seconds=time.perf_counter() - start,
        )

    with tracer.start_as_current_span(f"gemini.{operation}") as span:
        span.set_attribute("gemini.operation", operation)
        span.set_attribute("gemini.max_retries", max_retries)

        last_exc: Exception | None = None
        last_was_rate_limit = False
        for attempt in range(1, max_retries + 1):
            try:
                result = fn()
                _record("success")
                return result
            except httpx.TimeoutException as exc:
                last_exc = exc
                last_was_rate_limit = False
                logger.warning(
                    "%s timed out (attempt %d/%d)", operation, attempt, max_retries
                )
            except genai_errors.APIError as exc:
                last_exc = exc

                if exc.code in _AUTH_ERROR_CODES:
                    logger.error(
                        "%s failed with authentication error %s — not retrying "
                        "(invalid or revoked API key)",
                        operation,
                        exc.code,
                        exc_info=exc,
                    )
                    _record("auth_error")
                    raise AIServiceError(
                        f"{operation} could not be completed because the AI service "
                        "rejected the request."
                    ) from exc

                retryable = exc.code == 429 or (
                    exc.code is not None and exc.code >= 500
                )
                last_was_rate_limit = exc.code == 429
                if not retryable:
                    logger.error(
                        "%s failed with non-retryable API error %s: %s",
                        operation,
                        exc.code,
                        exc,
                        exc_info=exc,
                    )
                    _record("error")
                    raise AIServiceError(
                        f"{operation} could not be completed because the AI service "
                        "rejected the request."
                    ) from exc
                logger.warning(
                    "%s failed with retryable API error %s (attempt %d/%d)",
                    operation,
                    exc.code,
                    attempt,
                    max_retries,
                )

            if attempt < max_retries:
                time.sleep(backoff_base * (2 ** (attempt - 1)))

        logger.error(
            "%s failed after %d attempt(s): %s",
            operation,
            max_retries,
            last_exc,
            exc_info=last_exc,
        )

        if last_was_rate_limit:
            _record("rate_limited")
            raise AIServiceError(
                RATE_LIMIT_MESSAGE,
                status_code=429,
            ) from last_exc

        _record("error")
        raise AIServiceError(
            f"{operation} is currently unavailable. Please try again shortly."
        ) from last_exc


def strip_fences(text: str) -> str:
    """Remove markdown code fences from Gemini output before JSON parsing."""
    match = _FENCE_RE.search(text)
    if match:
        return match.group(1)
    return text.strip()


def _repair_and_parse(stripped: str, *, expect: type) -> object | None:
    """Attempt to recover valid JSON from text with leading/trailing noise.

    Gemini occasionally prepends or appends commentary outside the fenced
    block (e.g. "Sure, here is the JSON:\\n{...}\\nLet me know if..."). This
    extracts the substring between the first opening bracket and the
    matching closing bracket for the expected type and retries parsing.
    Returns None if repair is not possible or still fails — never raises.
    """
    open_ch, close_ch = ("{", "}") if expect is dict else ("[", "]")
    start = stripped.find(open_ch)
    end = stripped.rfind(close_ch)
    if start == -1 or end == -1 or end <= start:
        return None
    candidate = stripped[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def parse_json_response(
    raw_text: str,
    *,
    operation: str,
    expect: type = dict,
) -> object:
    """Safely parse Gemini output that is expected to be JSON.

    Never assumes Gemini returned valid JSON: strips markdown fences, then
    attempts ``json.loads``. If that fails, attempts one automatic repair
    pass that extracts the substring between the outermost matching
    brackets (handles stray commentary around an otherwise-valid JSON
    blob). Raises ``AIServiceError`` (502) with a generic detail on total
    failure — the raw response is logged for diagnosis but never returned
    to the client.

    Args:
        raw_text: The raw text from the Gemini response.
        operation: Human-readable operation name, used in log messages and
            the generic error detail.
        expect: ``dict`` (default) or ``list`` — the JSON top-level type
            this response must parse into.
    """
    stripped = strip_fences(raw_text)

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        parsed = _repair_and_parse(stripped, expect=expect)
        if parsed is None:
            logger.error(
                "%s: Gemini returned non-JSON response. Raw output follows:\n%s",
                operation,
                raw_text,
            )
            raise AIServiceError(
                f"{operation} returned an invalid response. Please try again."
            )
        logger.warning(
            "%s: Gemini response required JSON repair before parsing.", operation
        )

    if not isinstance(parsed, expect):
        logger.error(
            "%s: Gemini returned JSON but not a %s. Type=%s. Raw output:\n%s",
            operation,
            expect.__name__,
            type(parsed).__name__,
            raw_text,
        )
        raise AIServiceError(f"{operation} returned an unexpected response format.")

    return parsed
