"""Benchmark service — percentile rankings across all users."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analysis import InterviewAnalysis, AudioResponse
from app.models.interview import InterviewSession
from app.services import prediction_service


def get_user_benchmark(user_id: uuid.UUID, db: Session) -> dict:
    """Compute the current user's percentile rank vs all platform users."""
    stmt = (
        select(InterviewAnalysis.overall_score)
        .join(AudioResponse, InterviewAnalysis.audio_response_id == AudioResponse.id)
        .join(InterviewSession, AudioResponse.session_id == InterviewSession.id)
    )
    all_rows = db.execute(stmt).scalars().all()
    all_scores = [float(s) for s in all_rows if s is not None]

    user_stmt = (
        select(InterviewAnalysis.overall_score)
        .join(AudioResponse, InterviewAnalysis.audio_response_id == AudioResponse.id)
        .join(InterviewSession, AudioResponse.session_id == InterviewSession.id)
        .where(InterviewSession.user_id == user_id)
    )
    user_rows = db.execute(user_stmt).scalars().all()
    user_scores = [float(s) for s in user_rows if s is not None]

    if not user_scores:
        return {
            "user_average_score": None,
            "percentile_rank": None,
            "total_platform_responses": len(all_scores),
            "user_responses_analyzed": 0,
        }

    user_avg = round(sum(user_scores) / len(user_scores), 2)
    percentile = prediction_service.compute_percentile(user_avg, all_scores)

    return {
        "user_average_score": user_avg,
        "percentile_rank": percentile,
        "total_platform_responses": len(all_scores),
        "user_responses_analyzed": len(user_scores),
    }
