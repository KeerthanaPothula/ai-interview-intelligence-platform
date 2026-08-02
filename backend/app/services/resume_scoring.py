"""Deterministic resume ATS-score heuristic.

Shared between the resume analysis endpoint's Gemini-failure fallback and
the recruiter dashboard, which needs an ATS estimate for every candidate in
a list response and cannot afford one Gemini call per row.
"""

from __future__ import annotations


def estimate_ats_score(word_count: int) -> int:
    """Estimate an ATS pass-rate score from resume word count.

    Longer resumes (within reason) tend to have more quantifiable content
    and keyword coverage. Clamped to [40, 90] — this is a cheap fallback
    heuristic, not a substitute for the Gemini-scored analysis.
    """
    return max(40, min(90, 40 + word_count // 20))
