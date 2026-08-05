from __future__ import annotations

import logging
import threading

from google import genai

from app.config import get_settings
from app.core.ai_reliability import (
    call_gemini_with_retry,
    parse_json_response,
    strip_fences,
)
from app.core.exceptions import AIServiceError
from app.models.interview import (
    QUESTION_CATEGORY_BEHAVIORAL,
    VALID_QUESTION_CATEGORIES,
)

logger = logging.getLogger(__name__)

_VALID_CATEGORIES = (
    VALID_QUESTION_CATEGORIES  # {"behavioral", "technical", "situational"}
)


def _build_client() -> genai.Client:
    settings = get_settings()
    return genai.Client(
        api_key=settings.GEMINI_API_KEY,
        # google-genai's HttpOptions.timeout is in milliseconds, but
        # GEMINI_TIMEOUT_SECONDS is (as its name says) seconds — convert here.
        http_options={"timeout": settings.GEMINI_TIMEOUT_SECONDS * 1000},
    )


# Lazy singleton — same rationale as evaluation_service: defer API-key reads
# and HTTP pool creation to the first actual request, reducing cold-start
# latency and avoiding import-time failures in non-production environments.
_client: genai.Client | None = None
_client_lock = threading.Lock()


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = _build_client()
    return _client


def _build_prompt(job_role: str, job_description: str, count: int) -> str:
    return f"""You are a senior technical interviewer preparing questions for a {job_role} position.

Job description:
{job_description}

Generate exactly {count} interview questions tailored to this role and description.

Return ONLY a valid JSON array. Do not include any explanation, markdown formatting, or text outside the JSON array.

Each element must be a JSON object with exactly these fields:
  "body"     - the full question text (non-empty string)
  "category" - exactly one of: "behavioral", "technical", "situational"

Example format:
[
  {{"body": "Describe a time you resolved a production incident.", "category": "behavioral"}},
  {{"body": "How would you design a rate limiter?", "category": "technical"}}
]

Requirements:
- Include a mix of all three categories where appropriate for the role.
- Questions must be specific to the job description, not generic.
- Return exactly {count} questions.
- Do not include a "sequence_order" field — ordering is handled by the application."""


def _validate_and_normalize(raw: list[object], count: int) -> list[dict]:
    """Validate each item from the parsed Gemini JSON response.

    Applies three rules:
    1. body must be a non-empty string.
    2. category must be one of the three allowed values; items with an
       unrecognised category are assigned "behavioral" as a safe fallback
       rather than being dropped (dropping would reduce question count).
    3. sequence_order is assigned as index + 1 — Gemini's own value (if
       present) is ignored. This guarantees a dense 1-based sequence that
       will never violate the UniqueConstraint on (session_id, sequence_order).

    Processing stops once count valid items have been collected; any excess
    items returned by Gemini are silently truncated.
    Items that fail rule 1 are dropped with a warning. The caller raises
    HTTP 502 if the final list contains fewer than count valid questions.
    """
    normalized: list[dict] = []
    for i, item in enumerate(raw):
        if len(normalized) == count:
            logger.warning(
                "Gemini returned more than %d questions; truncating excess.", count
            )
            break

        if not isinstance(item, dict):
            logger.warning("Gemini returned non-object item at index %d: %r", i, item)
            continue

        body = item.get("body", "")
        if not isinstance(body, str) or not body.strip():
            logger.warning("Gemini returned empty/missing body at index %d", i)
            continue

        raw_category = item.get("category", "")
        if raw_category not in _VALID_CATEGORIES:
            logger.warning(
                "Gemini returned unknown category %r at index %d; defaulting to 'behavioral'",
                raw_category,
                i,
            )
            category = QUESTION_CATEGORY_BEHAVIORAL
        else:
            category = raw_category

        normalized.append(
            {
                "body": body.strip(),
                "category": category,
                "sequence_order": len(normalized) + 1,
            }
        )

    return normalized


def generate_questions(
    job_role: str,
    job_description: str,
    count: int,
) -> list[dict]:
    """Call Gemini to generate interview questions and return a normalized list.

    Calls Gemini → strips markdown fences → parses JSON → validates each item
    → assigns sequence_order → returns the normalized list.

    Return shape (each dict):
        {
            "body": str,          # non-empty question text
            "category": str,      # one of behavioral / technical / situational
            "sequence_order": int # 1-based, dense, assigned by this function
        }

    Raises:
        AIServiceError 502 — Gemini times out, is unreachable, returns
                             invalid JSON, or returns fewer than count valid
                             questions after normalization.
        AIServiceError 429 — Gemini rate limit still exceeded after retries.

    Prompt-injection note:
        job_role and job_description are user-supplied strings interpolated into
        the prompt. A malicious input could attempt to override the instructions.
        The risk is limited because: (a) the response is validated against a
        strict JSON schema — injected text that is not valid JSON is caught as a
        parse error; (b) the response is stored as question text, never executed.
        Input sanitization and response content moderation are Week 5+ concerns.

    Gemini 2.x compatibility:
        Uses client.models.generate_content() from the google-genai v2 SDK.
        The model name comes from settings.GEMINI_MODEL (centralized config)
        so it can be updated in one place without touching this function's
        signature. The SDK response always exposes .text for text-mode
        generation; structured output (response_schema) is a future option
        if stricter output validation is needed.
    """
    prompt = _build_prompt(job_role, job_description, count)
    model = get_settings().GEMINI_MODEL
    client = _get_client()

    response = call_gemini_with_retry(
        lambda: client.models.generate_content(model=model, contents=prompt),
        operation="Question generation",
    )
    raw_text: str = response.text

    parsed = parse_json_response(raw_text, operation="Question generation", expect=list)

    questions = _validate_and_normalize(parsed, count)

    if not questions:
        logger.error(
            "Gemini response contained no valid questions after validation. Raw output:\n%s",
            raw_text,
        )
        raise AIServiceError(
            "Question generation produced no usable questions. Please try again."
        )

    if len(questions) < count:
        logger.error(
            "Gemini returned %d valid question(s) but %d were requested. Raw output:\n%s",
            len(questions),
            count,
            raw_text,
        )
        raise AIServiceError(
            "Question generation returned fewer questions than expected. Please try again."
        )

    return questions


def generate_text(prompt: str) -> str:
    """Call Gemini with an arbitrary prompt and return the raw text response.

    Used for flexible AI tasks (resume analysis, insights, etc.).
    Raises RuntimeError on failure so callers can apply their own fallback —
    this is the one Gemini call site in the app that is expected to fail
    open (callers fall back to a non-AI heuristic) rather than surface an
    HTTP error, so AIServiceError is caught here and translated rather than
    left to propagate.
    """
    model = get_settings().GEMINI_MODEL
    client = _get_client()
    try:
        response = call_gemini_with_retry(
            lambda: client.models.generate_content(model=model, contents=prompt),
            operation="Free-form text generation",
        )
        raw: str = response.text
        return strip_fences(raw)
    except AIServiceError as exc:
        logger.warning("generate_text failed: %s", exc.detail)
        raise RuntimeError(exc.detail) from exc
