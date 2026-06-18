"""AI Career Coach — Gemini-generated 7/14/30-day improvement plans."""

from __future__ import annotations

import json
import logging

import google.genai as genai

from app.config import get_settings

logger = logging.getLogger(__name__)

_MODEL = "gemini-2.0-flash"
_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        settings = get_settings()
        _client = genai.Client(
            api_key=settings.GEMINI_API_KEY,
            http_options={"timeout": 30},
        )
    return _client


def generate_coaching_plan(
    *,
    job_role: str,
    job_description: str,
    overall_score: float,
    communication_score: float,
    technical_score: float,
    problem_solving_score: float,
    readiness_level: str | None = None,
    weaknesses: list[str] | None = None,
) -> dict:
    """Generate a 7/14/30-day coaching plan via Gemini.

    Returns a dict with keys: plan_7_day, plan_14_day, plan_30_day,
    focus_areas, model_used.
    """
    client = _get_client()

    weaknesses_text = (
        "\n".join(f"- {w}" for w in weaknesses) if weaknesses else "Not specified"
    )
    readiness_text = readiness_level or "Developing"

    prompt = (
        f"You are an AI career coach helping a candidate prepare for a {job_role} role.\n\n"
        f"Job Description: {job_description[:500]}\n\n"
        f"Current Performance:\n"
        f"- Overall score: {overall_score:.1f}/10 ({readiness_text})\n"
        f"- Communication: {communication_score:.1f}/10\n"
        f"- Technical: {technical_score:.1f}/10\n"
        f"- Problem Solving: {problem_solving_score:.1f}/10\n\n"
        f"Key areas to improve:\n{weaknesses_text}\n\n"
        "Create a personalised improvement plan with specific, actionable steps.\n\n"
        "Return a JSON object with these exact keys (no markdown fences):\n"
        "{\n"
        '  "plan_7_day": ["Day 1-2: ...", "Day 3-4: ...", "Day 5-7: ..."],\n'
        '  "plan_14_day": ["Week 1: ...", "Week 2: ..."],\n'
        '  "plan_30_day": ["Week 1-2: ...", "Week 3-4: ..."],\n'
        '  "focus_areas": ["area1", "area2", "area3"]\n'
        "}"
    )

    response = client.models.generate_content(model=_MODEL, contents=prompt)
    raw = response.text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    parsed = json.loads(raw)
    parsed["model_used"] = _MODEL
    return parsed
