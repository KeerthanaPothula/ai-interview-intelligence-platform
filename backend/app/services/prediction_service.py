"""Interview Readiness Score — a transparent, deterministic weighted average.

This is NOT a machine-learned prediction of real-world hiring outcomes and
makes no claim to be one. It is a fixed weighted-average formula over the
same per-response signals already shown elsewhere in the product (Gemini
evaluation scores + voice analytics), meant to summarise a session's signals
into one number. There is no training step and no model — the weights below
are the entire "algorithm," and they are intentionally documented in full
here (and in docs/AI_PIPELINE.md) rather than hidden inside a fitted model.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

SCORING_METHOD = "weighted-v1"

# Weights sum to 1.0 across the four 0-10 component scores and the 0-10
# (confidence/10) term; filler words are a penalty subtracted afterwards,
# not part of the weighted sum, so the sum below intentionally excludes it.
_WEIGHT_OVERALL = 0.30
_WEIGHT_COMMUNICATION = 0.20
_WEIGHT_TECHNICAL = 0.25
_WEIGHT_PROBLEM_SOLVING = 0.15
_WEIGHT_CONFIDENCE = 0.10
_FILLER_PENALTY_PER_5_WORDS = 0.05

_READINESS_LEVELS: tuple[tuple[float, str], ...] = (
    (0.80, "Excellent"),
    (0.60, "Strong"),
    (0.40, "Developing"),
)
_LOWEST_READINESS_LEVEL = "Needs Improvement"


def compute_readiness(
    *,
    overall_score: float,
    communication_score: float,
    technical_score: float,
    problem_solving_score: float,
    avg_confidence: float = 60.0,
    avg_speaking_rate: float = 130.0,
    avg_filler_words: float = 3.0,
) -> tuple[float, str]:
    """Return (readiness_score, readiness_level) for a session's signals.

    readiness_score is in [0.0, 1.0] — a weighted average of the session's
    own component scores (each already 0-10), normalised to 0-1, with a
    small penalty for filler-word density. avg_speaking_rate is accepted
    for signature compatibility with callers but is not currently weighted
    (speaking rate has no single "better" direction the way the other
    signals do — see docs/AI_PIPELINE.md).

    readiness_level buckets the score into a human-readable label. Neither
    value is a prediction of a real-world interview or hiring outcome.
    """
    del avg_speaking_rate  # accepted for signature stability; not weighted

    weighted_0_10 = (
        _WEIGHT_OVERALL * overall_score
        + _WEIGHT_COMMUNICATION * communication_score
        + _WEIGHT_TECHNICAL * technical_score
        + _WEIGHT_PROBLEM_SOLVING * problem_solving_score
        + _WEIGHT_CONFIDENCE * (avg_confidence / 10)
    )
    filler_penalty = _FILLER_PENALTY_PER_5_WORDS * (avg_filler_words / 5)
    weighted_0_10 = max(0.0, min(10.0, weighted_0_10 - filler_penalty))

    readiness_score = round(weighted_0_10 / 10, 4)

    level = _LOWEST_READINESS_LEVEL
    for threshold, label in _READINESS_LEVELS:
        if readiness_score >= threshold:
            level = label
            break

    return readiness_score, level


def compute_percentile(user_score: float, all_scores: list[float]) -> float:
    """Return percentile rank (0-100) of user_score relative to all_scores."""
    if not all_scores:
        return 50.0
    below = sum(1 for s in all_scores if s < user_score)
    return compute_percentile_from_counts(below, len(all_scores))


def compute_percentile_from_counts(below: int, total: int) -> float:
    """Return percentile rank (0-100) given a precomputed below/total count.

    Lets callers compute `below` and `total` via a SQL aggregate (COUNT)
    instead of fetching every row into Python just to count them.
    """
    if not total:
        return 50.0
    return round(100.0 * below / total, 1)
