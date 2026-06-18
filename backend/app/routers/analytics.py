"""Analytics dashboard endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.models.analysis import AudioResponse, InterviewAnalysis
from app.models.interview import InterviewSession
from app.models.user import User
from app.schemas.features import AnalyticsOverviewResponse, SessionTrendResponse

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])


@router.get("/overview", response_model=AnalyticsOverviewResponse)
def get_analytics_overview(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalyticsOverviewResponse:
    """Return high-level performance metrics for the current user."""
    user_id: uuid.UUID = current_user.id

    total_sessions = (
        db.query(InterviewSession)
        .filter(InterviewSession.user_id == user_id)
        .count()
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
    if total_responses_analyzed >= 2:
        base_q = (
            db.query(InterviewAnalysis.overall_score, InterviewAnalysis.created_at)
            .join(AudioResponse, InterviewAnalysis.audio_response_id == AudioResponse.id)
            .filter(AudioResponse.user_id == user_id)
            .order_by(InterviewAnalysis.created_at)
        )
        rows = base_q.all()
        if rows:
            first_score = float(rows[0].overall_score)
            last_score = float(rows[-1].overall_score)
            improvement_score = round(last_score - first_score, 1)

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

    sessions = (
        db.query(InterviewSession)
        .filter(InterviewSession.user_id == user_id)
        .order_by(InterviewSession.created_at)
        .all()
    )

    result: list[SessionTrendResponse] = []
    for session in sessions:
        avg_row = (
            db.query(
                func.avg(InterviewAnalysis.overall_score).label("overall"),
                func.avg(InterviewAnalysis.communication_score).label("comm"),
                func.avg(InterviewAnalysis.technical_score).label("tech"),
                func.avg(InterviewAnalysis.problem_solving_score).label("ps"),
                func.avg(InterviewAnalysis.confidence_score).label("conf"),
            )
            .join(AudioResponse, InterviewAnalysis.audio_response_id == AudioResponse.id)
            .filter(AudioResponse.session_id == session.id)
            .one()
        )

        def _f(v: object) -> float | None:
            return round(float(v), 1) if v is not None else None  # type: ignore[arg-type]

        result.append(
            SessionTrendResponse(
                session_id=session.id,
                session_title=session.title,
                created_at=session.created_at,
                average_overall_score=_f(avg_row.overall),
                average_communication_score=_f(avg_row.comm),
                average_technical_score=_f(avg_row.tech),
                average_problem_solving_score=_f(avg_row.ps),
                average_confidence_score=_f(avg_row.conf),
            )
        )

    return result
