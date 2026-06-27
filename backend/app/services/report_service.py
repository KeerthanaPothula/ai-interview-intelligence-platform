"""Session-Level Final Report — Gemini-generated holistic evaluation."""

from __future__ import annotations

import json
import logging
from typing import Any

from google import genai

from app.config import get_settings
from app.core.ai_reliability import call_gemini_with_retry, parse_json_response

logger = logging.getLogger(__name__)

READINESS_LEVELS = [
    "Beginner",
    "Developing",
    "Interview Ready",
    "Strong Candidate",
    "Highly Competitive",
]


def _build_client() -> genai.Client:
    settings = get_settings()
    return genai.Client(
        api_key=settings.GEMINI_API_KEY,
        http_options={"timeout": settings.GEMINI_TIMEOUT_SECONDS},
    )


_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = _build_client()
    return _client


def _safe_mean(values: list[float]) -> float | None:
    valid = [v for v in values if v is not None]
    return round(sum(valid) / len(valid), 1) if valid else None


def generate_session_report(
    *,
    job_role: str,
    job_description: str,
    questions_and_transcripts: list[dict[str, Any]],
    analyses: list[dict[str, Any]],
    voice_analytics: list[dict[str, Any]],
) -> dict:
    """Generate a holistic session report using Gemini.

    Args:
        job_role: The target job role for the session.
        job_description: Full job description text.
        questions_and_transcripts: list of {question, transcript} dicts.
        analyses: list of InterviewAnalysis dicts with score fields.
        voice_analytics: list of VoiceAnalysis dicts; may be empty.

    Returns:
        dict with keys: overall_performance, final_score, confidence_score,
        communication_score, technical_score, problem_solving_score,
        strengths (JSON str), weaknesses (JSON str), improvement_plan (JSON str),
        readiness_level, model_used.
    """

    # ------------------------------------------------------------------
    # Aggregate numeric scores
    # ------------------------------------------------------------------
    def _extract(key: str) -> list[float]:
        return [float(a[key]) for a in analyses if a.get(key) is not None]

    final_score = _safe_mean(_extract("overall_score"))
    communication_score = _safe_mean(_extract("communication_score"))
    technical_score = _safe_mean(_extract("technical_score"))
    problem_solving_score = _safe_mean(_extract("problem_solving_score"))

    voice_confidence_scores = [
        v["confidence_score"]
        for v in voice_analytics
        if v.get("confidence_score") is not None
    ]
    avg_voice_confidence = (
        int(sum(voice_confidence_scores) / len(voice_confidence_scores))
        if voice_confidence_scores
        else None
    )

    # ------------------------------------------------------------------
    # Build prompt
    # ------------------------------------------------------------------
    qa_summary = ""
    for i, qt in enumerate(questions_and_transcripts[:10], 1):
        q = qt.get("question", "")
        t = qt.get("transcript", "")[:500]
        qa_summary += f"\nQ{i}: {q}\nA{i} (excerpt): {t}\n"

    score_summary = (
        f"Overall: {final_score}/10, "
        f"Communication: {communication_score}/10, "
        f"Technical: {technical_score}/10, "
        f"Problem Solving: {problem_solving_score}/10"
    )

    prompt = (
        "You are a senior hiring manager evaluating a job interview.\n\n"
        f"Role: {job_role}\n"
        f"Job Description: {job_description[:800]}\n\n"
        f"Interview Q&A Summary:{qa_summary}\n"
        f"AI Score Summary: {score_summary}\n\n"
        "Generate a structured evaluation as valid JSON (no markdown fences) "
        "with this exact shape:\n"
        "{\n"
        '  "overall_performance": "<2-3 sentence narrative summary>",\n'
        '  "strengths": ["<bullet 1>", "<bullet 2>", "<bullet 3>"],\n'
        '  "weaknesses": ["<bullet 1>", "<bullet 2>"],\n'
        '  "improvement_plan": ["<step 1>", "<step 2>", "<step 3>"],\n'
        f'  "readiness_level": "<one of: {", ".join(READINESS_LEVELS)}>"\n'
        "}\n"
        "Be specific, constructive, and grounded in the Q&A evidence."
    )

    client = _get_client()
    settings = get_settings()
    response = call_gemini_with_retry(
        lambda: client.models.generate_content(
            model=settings.GEMINI_MODEL, contents=prompt
        ),
        operation="Session report generation",
    )
    parsed = parse_json_response(
        response.text, operation="Session report generation", expect=dict
    )

    strengths = parsed.get("strengths", [])
    weaknesses = parsed.get("weaknesses", [])
    improvement_plan = parsed.get("improvement_plan", [])
    readiness_level = parsed.get("readiness_level", "Developing")

    if readiness_level not in READINESS_LEVELS:
        readiness_level = "Developing"

    logger.info(
        "Session report generated: readiness=%r, final_score=%s",
        readiness_level,
        final_score,
    )

    return {
        "overall_performance": parsed.get("overall_performance", ""),
        "final_score": final_score,
        "confidence_score": avg_voice_confidence,
        "communication_score": communication_score,
        "technical_score": technical_score,
        "problem_solving_score": problem_solving_score,
        "strengths": json.dumps(strengths),
        "weaknesses": json.dumps(weaknesses),
        "improvement_plan": json.dumps(improvement_plan),
        "readiness_level": readiness_level,
        "model_used": settings.GEMINI_MODEL,
    }
