"""Analytics dashboard endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.constants import API_V1_PREFIX
from app.core.deps import get_current_user
from app.database import get_db
from app.models.analysis import AudioResponse, InterviewAnalysis
from app.models.interview import InterviewSession
from app.models.user import User
from app.schemas.features import AnalyticsOverviewResponse, SessionTrendResponse

router = APIRouter(prefix=f"{API_V1_PREFIX}/analytics", tags=["Analytics"])


@router.get("/overview", response_model=AnalyticsOverviewResponse)
def get_analytics_overview(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalyticsOverviewResponse:
    """Return high-level performance metrics for the current user."""
    user_id: uuid.UUID = current_user.id

    total_sessions = (
        db.query(InterviewSession).filter(InterviewSession.user_id == user_id).count()
    )
    completed_sessions = (
        db.query(InterviewSession)
        .filter(
            InterviewSession.user_id == user_id,
            InterviewSession.status == "completed",
        )
        .count()
    )

    # Join through AudioResponse to reach InterviewAnalysis for this user.
    analyses_query = (
        db.query(InterviewAnalysis)
        .join(AudioResponse, InterviewAnalysis.audio_response_id == AudioResponse.id)
        .filter(AudioResponse.user_id == user_id)
    )
    total_responses_analyzed = analyses_query.count()

    avg_row = (
        db.query(
            func.avg(InterviewAnalysis.overall_score).label("overall"),
            func.avg(InterviewAnalysis.communication_score).label("comm"),
            func.avg(InterviewAnalysis.technical_score).label("tech"),
            func.avg(InterviewAnalysis.problem_solving_score).label("ps"),
        )
        .join(AudioResponse, InterviewAnalysis.audio_response_id == AudioResponse.id)
        .filter(AudioResponse.user_id == user_id)
        .one()
    )

    average_overall_score = (
        round(float(avg_row.overall), 1) if avg_row.overall is not None else None
    )

    # Strongest / weakest skill from category averages.
    strongest_skill: str | None = None
    weakest_skill: str | None = None
    improvement_score: float | None = None

    if avg_row.comm is not None:
        skill_scores = {
            "Communication": round(float(avg_row.comm), 1),
            "Technical": round(float(avg_row.tech), 1),
            "Problem Solving": round(float(avg_row.ps), 1),
        }
        strongest_skill = max(skill_scores, key=lambda k: skill_scores[k])
        weakest_skill = min(skill_scores, key=lambda k: skill_scores[k])

    # Improvement: latest overall score minus first overall score.
    # Two LIMIT 1 queries instead of loading all rows — O(1) instead of O(N).
    if total_responses_analyzed >= 2:
        _base = (
            db.query(InterviewAnalysis.overall_score)
            .join(
                AudioResponse, InterviewAnalysis.audio_response_id == AudioResponse.id
            )
            .filter(AudioResponse.user_id == user_id)
        )
        first_score_val = _base.order_by(InterviewAnalysis.created_at).limit(1).scalar()
        last_score_val = (
            _base.order_by(InterviewAnalysis.created_at.desc()).limit(1).scalar()
        )
        if first_score_val is not None and last_score_val is not None:
            improvement_score = round(float(last_score_val) - float(first_score_val), 1)

    return AnalyticsOverviewResponse(
        total_sessions=total_sessions,
        completed_sessions=completed_sessions,
        average_overall_score=average_overall_score,
        total_responses_analyzed=total_responses_analyzed,
        strongest_skill=strongest_skill,
        weakest_skill=weakest_skill,
        improvement_score=improvement_score,
    )


@router.get("/trends", response_model=list[SessionTrendResponse])
def get_analytics_trends(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SessionTrendResponse]:
    """Return per-session score averages for trend charts."""
    user_id: uuid.UUID = current_user.id

    def _f(v: object) -> float | None:
        return round(float(v), 1) if v is not None else None  # type: ignore[arg-type]

    # Single GROUP BY query replaces the previous N+1 pattern (one query per
    # session). OUTER JOINs preserve sessions that have no analyses yet so
    # they appear in the trend with null scores rather than being silently
    # dropped.
    rows = (
        db.query(
            InterviewSession.id.label("session_id"),
            InterviewSession.title.label("session_title"),
            InterviewSession.created_at.label("created_at"),
            func.avg(InterviewAnalysis.overall_score).label("overall"),
            func.avg(InterviewAnalysis.communication_score).label("comm"),
            func.avg(InterviewAnalysis.technical_score).label("tech"),
            func.avg(InterviewAnalysis.problem_solving_score).label("ps"),
            func.avg(InterviewAnalysis.confidence_score).label("conf"),
        )
        .outerjoin(AudioResponse, AudioResponse.session_id == InterviewSession.id)
        .outerjoin(
            InterviewAnalysis,
            InterviewAnalysis.audio_response_id == AudioResponse.id,
        )
        .filter(InterviewSession.user_id == user_id)
        .group_by(
            InterviewSession.id,
            InterviewSession.title,
            InterviewSession.created_at,
        )
        .order_by(InterviewSession.created_at)
        .all()
    )

    return [
        SessionTrendResponse(
            session_id=row.session_id,
            session_title=row.session_title,
            created_at=row.created_at,
            average_overall_score=_f(row.overall),
            average_communication_score=_f(row.comm),
            average_technical_score=_f(row.tech),
            average_problem_solving_score=_f(row.ps),
            average_confidence_score=_f(row.conf),
        )
        for row in rows
    ]
