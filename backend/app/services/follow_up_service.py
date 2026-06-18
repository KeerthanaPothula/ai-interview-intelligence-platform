"""AI Follow-Up Interviewer — Gemini-powered follow-up question generation."""

from __future__ import annotations

import logging

from google import genai

from app.config import get_settings

logger = logging.getLogger(__name__)

_MODEL = "gemini-2.0-flash"


def _build_client() -> genai.Client:
    settings = get_settings()
    return genai.Client(
        api_key=settings.GEMINI_API_KEY,
        http_options={"timeout": 30},
    )


_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = _build_client()
    return _client


def generate_follow_up_question(
    *,
    original_question: str,
    transcript_text: str,
    job_role: str,
    job_description: str,
) -> str:
    """Generate a targeted follow-up question using Gemini.

    The follow-up probes deeper into an aspect of the candidate's answer
    that was vague, interesting, or worth elaborating on.

    Returns:
        A single follow-up question as a plain string.
    """
    prompt = (
        "You are an experienced technical interviewer conducting a job interview.\n\n"
        f"Job Role: {job_role}\n"
        f"Job Description: {job_description}\n\n"
        f"Original Question: {original_question}\n\n"
        f"Candidate's Answer:\n{transcript_text[:3000]}\n\n"
        "Based on the candidate's answer, generate ONE concise follow-up question "
        "that:\n"
        "- Probes deeper into something the candidate mentioned\n"
        "- Asks for a specific example they did not provide\n"
        "- Clarifies an ambiguous or vague statement\n"
        "- Explores a relevant area they overlooked\n\n"
        "Return ONLY the question text itself, with no prefix, numbering, "
        "or explanation."
    )

    client = _get_client()
    response = client.models.generate_content(model=_MODEL, contents=prompt)
    question_text = response.text.strip()

    if not question_text:
        raise ValueError("Gemini returned an empty follow-up question")

    logger.info(
        "Follow-up question generated for job_role=%r (length=%d chars)",
        job_role,
        len(question_text),
    )
    return question_text
