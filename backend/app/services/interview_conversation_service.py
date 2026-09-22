"""Live conversational AI interviewer — multi-turn Gemini-powered interviews."""

from __future__ import annotations

import logging

import google.genai as genai

from app.config import get_settings
from app.core.ai_reliability import call_gemini_with_retry
from app.core.exceptions import AIServiceError

logger = logging.getLogger(__name__)


def _require_text(response, operation: str) -> str:
    """Return response.text.strip(), or raise AIServiceError if Gemini
    returned no usable text.

    call_gemini_with_retry only catches transport errors and
    genai_errors.APIError — it never sees this case, because Gemini answers
    with a normal 200 OK. response.text is None (not an exception) whenever
    the response has no candidates or no content parts, which happens when
    the prompt or the model's own output is blocked (safety filters,
    recitation, etc.). Calling .strip() on that None is what previously
    surfaced as an unhandled AttributeError.
    """
    text = response.text
    if not text:
        logger.error(
            "%s: Gemini returned no usable text (response likely blocked by "
            "content/safety filtering).",
            operation,
        )
        raise AIServiceError(
            f"{operation} could not be completed because the AI did not "
            "return a usable response. Please try again."
        )
    return text.strip()


_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        settings = get_settings()
        _client = genai.Client(
            api_key=settings.GEMINI_API_KEY,
            # google-genai's HttpOptions.timeout is in milliseconds, but
            # GEMINI_TIMEOUT_SECONDS is (as its name says) seconds — convert here.
            http_options={"timeout": settings.GEMINI_TIMEOUT_SECONDS * 1000},
        )
    return _client


def generate_opening_question(job_role: str, job_description: str) -> str:
    """Generate the first question for a live interview."""
    client = _get_client()
    settings = get_settings()
    prompt = (
        f"You are an experienced technical interviewer for a {job_role} position.\n\n"
        f"Job Description:\n{job_description[:1000]}\n\n"
        "Start the interview with a warm, professional opening question. "
        "It should be a behavioral question suitable for the beginning of an interview. "
        "Return ONLY the question text, no preamble."
    )
    response = call_gemini_with_retry(
        lambda: client.models.generate_content(
            model=settings.GEMINI_MODEL, contents=prompt
        ),
        operation="Opening question generation",
    )
    return _require_text(response, "Opening question generation")


def generate_follow_up_question(
    *,
    job_role: str,
    job_description: str,
    conversation_history: list[dict],
    current_turn: int,
    max_turns: int,
) -> tuple[str, int]:
    """Generate the next interview question with increasing difficulty.

    Returns (question_text, difficulty_level) where difficulty_level is 1-5.
    """
    client = _get_client()
    settings = get_settings()

    difficulty = min(5, max(1, round(1 + (current_turn / max(max_turns - 1, 1)) * 4)))

    history_text = ""
    for turn in conversation_history:
        history_text += f"Q{turn['turn_number']}: {turn['question_text']}\n"
        if turn.get("response_text"):
            history_text += f"A{turn['turn_number']}: {turn['response_text'][:500]}\n"
        history_text += "\n"

    difficulty_labels = {
        1: "easy warm-up",
        2: "moderate",
        3: "intermediate",
        4: "challenging",
        5: "senior-level deep-dive",
    }

    prompt = (
        f"You are a technical interviewer for a {job_role} position.\n\n"
        f"Job Description: {job_description[:500]}\n\n"
        f"Interview conversation so far:\n{history_text}\n"
        f"This is question {current_turn + 1} of {max_turns}. "
        f"Generate a {difficulty_labels[difficulty]} question. "
        "Build on what the candidate has said, probe deeper on weaknesses, "
        "or explore a new relevant area. "
        "For higher difficulty levels, ask about system design, trade-offs, "
        "edge cases, or specific technical challenges. "
        "Return ONLY the question text, no preamble or explanation."
    )
    response = call_gemini_with_retry(
        lambda: client.models.generate_content(
            model=settings.GEMINI_MODEL, contents=prompt
        ),
        operation="Follow-up interview question generation",
    )
    text = _require_text(response, "Follow-up interview question generation")
    return text, difficulty


def generate_interview_summary(
    *,
    job_role: str,
    conversation_history: list[dict],
) -> str:
    """Generate a brief closing summary when the interview ends."""
    client = _get_client()
    settings = get_settings()

    history_text = "\n".join(
        f"Q{t['turn_number']}: {t['question_text']}\n"
        f"A{t['turn_number']}: {(t.get('response_text') or 'No response recorded')[:300]}"
        for t in conversation_history
    )

    prompt = (
        f"You conducted a live interview for a {job_role} candidate. "
        f"Here is the conversation:\n\n{history_text}\n\n"
        "Write a 2-3 sentence summary of how the interview went — "
        "highlight strengths and one area to work on. Be encouraging but honest. "
        "Return only the summary text."
    )
    response = call_gemini_with_retry(
        lambda: client.models.generate_content(
            model=settings.GEMINI_MODEL, contents=prompt
        ),
        operation="Interview summary generation",
    )
    return _require_text(response, "Interview summary generation")
