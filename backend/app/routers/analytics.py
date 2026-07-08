"""Analytics dashboard endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, union_all, literal, case
from sqlalchemy.orm import Session

from app.core.constants import API_V1_PREFIX
from app.core.deps import get_current_user
from app.database import get_db
from app.models.analysis import AudioResponse, InterviewAnalysis
from app.models.documents import ResumeDocument
from app.models.features import SessionReport
from app.models.interview import InterviewSession
from app.models.user import User
from app.schemas.features import (
    ActivityEvent,
    ActivityTimelineResponse,
    AnalyticsOverviewResponse,
    InsightItem,
    InsightsResponse,
    SessionTrendResponse,
)

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


@router.get("/activity", response_model=ActivityTimelineResponse)
def get_activity_timeline(
    limit: int = Query(default=20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ActivityTimelineResponse:
    """Return recent activity events for the current user."""
    user_id: uuid.UUID = current_user.id
    events: list[ActivityEvent] = []

    # Session created events
    sessions = (
        db.query(InterviewSession.title, InterviewSession.status, InterviewSession.created_at)
        .filter(InterviewSession.user_id == user_id)
        .order_by(InterviewSession.created_at.desc())
        .limit(limit)
        .all()
    )
    for s in sessions:
        events.append(ActivityEvent(
            event_type="session_created",
            title=f"Interview session created",
            subtitle=s.title,
            created_at=s.created_at,
        ))
        if s.status == "completed":
            events.append(ActivityEvent(
                event_type="session_completed",
                title="Interview completed",
                subtitle=s.title,
                created_at=s.created_at,
            ))

    # Report generated events
    reports = (
        db.query(SessionReport.session_id, SessionReport.created_at, InterviewSession.title)
        .join(InterviewSession, SessionReport.session_id == InterviewSession.id)
        .filter(InterviewSession.user_id == user_id)
        .order_by(SessionReport.created_at.desc())
        .limit(limit)
        .all()
    )
    for r in reports:
        events.append(ActivityEvent(
            event_type="report_generated",
            title="AI Report generated",
            subtitle=r.title,
            created_at=r.created_at,
        ))

    # Resume upload events
    resumes = (
        db.query(ResumeDocument.filename, ResumeDocument.created_at)
        .filter(ResumeDocument.user_id == user_id)
        .order_by(ResumeDocument.created_at.desc())
        .limit(5)
        .all()
    )
    for rv in resumes:
        events.append(ActivityEvent(
            event_type="resume_uploaded",
            title="Resume uploaded",
            subtitle=rv.filename,
            created_at=rv.created_at,
        ))

    events.sort(key=lambda e: e.created_at, reverse=True)
    return ActivityTimelineResponse(events=events[:limit])


@router.get("/insights", response_model=InsightsResponse)
def get_insights(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InsightsResponse:
    """Derive actionable insights from the user's interview performance data."""
    user_id: uuid.UUID = current_user.id
    insights: list[InsightItem] = []

    analyses_q = (
        db.query(InterviewAnalysis)
        .join(AudioResponse, InterviewAnalysis.audio_response_id == AudioResponse.id)
        .filter(AudioResponse.user_id == user_id)
    )

    total = analyses_q.count()
    if total == 0:
        insights.append(InsightItem(
            text="Complete your first interview session to unlock personalized insights.",
            kind="info",
        ))
        return InsightsResponse(insights=insights)

    avg = analyses_q.with_entities(
        func.avg(InterviewAnalysis.overall_score).label("overall"),
        func.avg(InterviewAnalysis.communication_score).label("comm"),
        func.avg(InterviewAnalysis.technical_score).label("tech"),
        func.avg(InterviewAnalysis.problem_solving_score).label("ps"),
        func.avg(InterviewAnalysis.confidence_score).label("conf"),
    ).one()

    now_utc = datetime.now(tz=timezone.utc)
    thirty_days_ago = now_utc - timedelta(days=30)

    recent_avg = (
        analyses_q
        .filter(InterviewAnalysis.created_at >= thirty_days_ago)
        .with_entities(
            func.avg(InterviewAnalysis.overall_score).label("overall"),
            func.avg(InterviewAnalysis.communication_score).label("comm"),
            func.avg(InterviewAnalysis.confidence_score).label("conf"),
        )
        .one()
    )

    def _fv(v: object) -> float:
        return float(v) if v is not None else 0.0

    overall = _fv(avg.overall)
    comm = _fv(avg.comm)
    tech = _fv(avg.tech)
    ps = _fv(avg.ps)
    conf = _fv(avg.conf)

    if overall >= 8.0:
        insights.append(InsightItem(text=f"Excellent overall score of {overall:.1f}/10 — you're interview-ready!", kind="positive"))
    elif overall >= 6.0:
        insights.append(InsightItem(text=f"Good average score of {overall:.1f}/10. A bit more practice will sharpen your edge.", kind="info"))
    else:
        insights.append(InsightItem(text=f"Average score is {overall:.1f}/10. Focus on targeted practice to improve.", kind="warning"))

    skill_map = {"Communication": comm, "Technical": tech, "Problem Solving": ps, "Confidence": conf}
    best_skill = max(skill_map, key=lambda k: skill_map[k])
    worst_skill = min(skill_map, key=lambda k: skill_map[k])
    insights.append(InsightItem(text=f"{best_skill} is your strongest area ({skill_map[best_skill]:.1f}/10) — great job!", kind="positive"))

    if skill_map[worst_skill] < 6.0:
        insights.append(InsightItem(text=f"{worst_skill} needs work ({skill_map[worst_skill]:.1f}/10). Consider targeted practice.", kind="warning"))

    if recent_avg.comm is not None and avg.comm is not None:
        delta = _fv(recent_avg.comm) - _fv(avg.comm)
        if delta > 0.5:
            insights.append(InsightItem(text=f"Communication improved by {delta:.1f} points in the last 30 days.", kind="positive"))
        elif delta < -0.5:
            insights.append(InsightItem(text="Communication score has dipped slightly this month — review your recent feedback.", kind="warning"))

    if total >= 3:
        completion_rate = min(100, int(total / max(1, total) * 100))
        insights.append(InsightItem(text=f"You've analyzed {total} responses. Keep up the momentum!", kind="info"))

    return InsightsResponse(insights=insights)
