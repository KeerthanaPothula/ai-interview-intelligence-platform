"""Benchmark service — percentile rankings across all users."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.analysis import InterviewAnalysis, AudioResponse
from app.models.interview import InterviewSession
from app.services import prediction_service


def get_user_benchmark(user_id: uuid.UUID, db: Session) -> dict:
    """Compute the current user's percentile rank vs all platform users.

    Uses SQL aggregates (COUNT/AVG) throughout instead of fetching every
    InterviewAnalysis row in the platform into Python — this query's cost no
    longer grows linearly with the total number of analyses on the platform.
    """
    total_count = db.execute(
        select(func.count(InterviewAnalysis.overall_score)).join(
            AudioResponse, InterviewAnalysis.audio_response_id == AudioResponse.id
        )
    ).scalar_one()

    user_avg_raw, user_count = db.execute(
        select(
            func.avg(InterviewAnalysis.overall_score),
            func.count(InterviewAnalysis.overall_score),
        )
        .join(AudioResponse, InterviewAnalysis.audio_response_id == AudioResponse.id)
        .join(InterviewSession, AudioResponse.session_id == InterviewSession.id)
        .where(InterviewSession.user_id == user_id)
    ).one()

    if not user_count:
        return {
            "user_average_score": None,
            "percentile_rank": None,
            "total_platform_responses": total_count,
            "user_responses_analyzed": 0,
        }

    user_avg = round(float(user_avg_raw), 2)

    below_count = db.execute(
        select(func.count(InterviewAnalysis.overall_score))
        .join(AudioResponse, InterviewAnalysis.audio_response_id == AudioResponse.id)
        .where(InterviewAnalysis.overall_score < user_avg)
    ).scalar_one()

    percentile = prediction_service.compute_percentile_from_counts(
        below_count, total_count
    )

    return {
        "user_average_score": user_avg,
        "percentile_rank": percentile,
        "total_platform_responses": total_count,
        "user_responses_analyzed": user_count,
    }
