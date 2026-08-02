"""Aggregation service for the admin dashboard.

Same access-model note as recruiter_service.py: the User model has no
role/organisation concept (see its docstring), so — consistent with the
precedent already set for /api/v1/recruiter — this is reachable by any
authenticated user rather than gated behind a role that doesn't exist in
the schema. Every number here is a real query against the existing tables;
nothing is mocked or hardcoded.
"""

from __future__ import annotations

import os
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.analysis import AudioResponse, InterviewAnalysis, Transcript
from app.models.documents import ResumeDocument
from app.models.features import SessionReport
from app.models.interview import InterviewSession, Question, VALID_SESSION_STATUSES
from app.models.prediction import CoachingPlan, InterviewPrediction
from app.models.user import User
from app.schemas.admin import (
    AdminActivityEvent,
    AdminOverviewResponse,
    AdminUserResponse,
    AiUsageStats,
    DailyCount,
    JobRoleCount,
    StorageStats,
)


def _as_aware_utc(dt: datetime) -> datetime:
    """SQLite (tests) can round-trip DateTime(timezone=True) values as naive."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _bucket_by_day(timestamps: list[datetime], days: int) -> list[DailyCount]:
    """Bucket a list of timestamps into daily counts for the trailing `days` days.

    Done in Python rather than SQL (e.g. func.date()) because SQLite and
    PostgreSQL don't share a portable date-truncation function — this
    dataset is small enough that a Python pass is simpler and dialect-safe.
    """
    now = datetime.now(timezone.utc)
    counts: Counter[str] = Counter()
    for ts in timestamps:
        counts[_as_aware_utc(ts).date().isoformat()] += 1

    buckets: list[DailyCount] = []
    for i in range(days - 1, -1, -1):
        day = (now - timedelta(days=i)).date().isoformat()
        buckets.append(DailyCount(date=day, count=counts.get(day, 0)))
    return buckets


def _resume_storage_bytes(db: Session) -> tuple[int, int]:
    """Sum resume file sizes from disk.

    ResumeDocument has no stored file_size column (unlike AudioResponse),
    so this is the only way to get a real number — stat() each file,
    skipping any that are missing rather than failing the whole request.
    """
    paths = db.execute(select(ResumeDocument.file_path)).scalars().all()
    total = 0
    count = 0
    for path in paths:
        try:
            total += os.path.getsize(path)
            count += 1
        except OSError:
            continue
    return total, count


def get_overview(db: Session) -> AdminOverviewResponse:
    total_users = db.query(User).count()
    total_sessions = db.query(InterviewSession).count()

    status_rows = db.execute(
        select(InterviewSession.status, func.count(InterviewSession.id)).group_by(
            InterviewSession.status
        )
    ).all()
    sessions_by_status = {status: 0 for status in VALID_SESSION_STATUSES}
    for status, count in status_rows:
        sessions_by_status[status] = count

    total_reports = db.query(SessionReport).count()
    avg_score_row = db.execute(select(func.avg(SessionReport.final_score))).scalar_one_or_none()
    avg_platform_score = round(float(avg_score_row), 2) if avg_score_row is not None else None

    total_resumes = db.query(ResumeDocument).count()

    ai_usage = AiUsageStats(
        questions_generated=db.query(Question).count(),
        transcriptions_completed=db.query(Transcript).count(),
        evaluations_completed=db.query(InterviewAnalysis).count(),
        reports_generated=total_reports,
        coaching_plans_generated=db.query(CoachingPlan).count(),
        predictions_generated=db.query(InterviewPrediction).count(),
    )

    audio_stats = db.execute(
        select(
            func.coalesce(func.sum(AudioResponse.file_size_bytes), 0),
            func.count(AudioResponse.id),
        )
    ).one()
    audio_bytes, audio_file_count = int(audio_stats[0]), int(audio_stats[1])

    resume_bytes, resume_file_count = _resume_storage_bytes(db)

    storage = StorageStats(
        audio_bytes=audio_bytes,
        audio_file_count=audio_file_count,
        resume_bytes=resume_bytes,
        resume_file_count=resume_file_count,
    )

    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    recent_signups = db.execute(
        select(User.created_at).where(User.created_at >= thirty_days_ago)
    ).scalars().all()
    recent_sessions = db.execute(
        select(InterviewSession.created_at).where(InterviewSession.created_at >= thirty_days_ago)
    ).scalars().all()

    return AdminOverviewResponse(
        total_users=total_users,
        total_sessions=total_sessions,
        sessions_by_status=sessions_by_status,
        total_reports=total_reports,
        avg_platform_score=avg_platform_score,
        total_resumes=total_resumes,
        ai_usage=ai_usage,
        storage=storage,
        signups_last_30_days=_bucket_by_day(list(recent_signups), 30),
        sessions_last_30_days=_bucket_by_day(list(recent_sessions), 30),
    )


def list_users(
    db: Session, *, search: str | None = None, skip: int = 0, limit: int = 20
) -> tuple[list[AdminUserResponse], int]:
    # Unlike recruiter_service.list_candidates, sorting here is by a plain
    # column (created_at) rather than a Python-computed aggregate score, so
    # SQL can do the filter + count + LIMIT/OFFSET directly — no need to
    # load every user into memory just to paginate.
    base_query = select(User)
    if search:
        needle = f"%{search.strip().lower()}%"
        base_query = base_query.where(
            func.lower(User.full_name).like(needle) | func.lower(User.email).like(needle)
        )

    total = db.execute(select(func.count()).select_from(base_query.subquery())).scalar_one()

    page = (
        db.execute(base_query.order_by(User.created_at.desc()).offset(skip).limit(limit))
        .scalars()
        .all()
    )

    if not page:
        return [], total

    user_ids = [u.id for u in page]
    session_rows = db.execute(
        select(
            InterviewSession.user_id,
            func.count(InterviewSession.id),
            func.max(InterviewSession.created_at),
        )
        .where(InterviewSession.user_id.in_(user_ids))
        .group_by(InterviewSession.user_id)
    ).all()
    sessions_by_user: dict[uuid.UUID, tuple[int, datetime | None]] = {
        row[0]: (row[1], row[2]) for row in session_rows
    }

    items = [
        AdminUserResponse(
            id=u.id,
            full_name=u.full_name,
            email=u.email,
            created_at=u.created_at,
            sessions_completed=sessions_by_user.get(u.id, (0, None))[0],
            latest_session_at=sessions_by_user.get(u.id, (0, None))[1],
        )
        for u in page
    ]
    return items, total


def list_job_roles(db: Session) -> list[JobRoleCount]:
    rows = db.execute(
        select(InterviewSession.job_role, func.count(InterviewSession.id))
        .group_by(InterviewSession.job_role)
        .order_by(func.count(InterviewSession.id).desc())
    ).all()
    return [JobRoleCount(role=role, session_count=count) for role, count in rows]


def list_activity(db: Session, *, limit: int = 20) -> list[AdminActivityEvent]:
    events: list[AdminActivityEvent] = []

    sessions = db.execute(
        select(
            InterviewSession.title,
            InterviewSession.job_role,
            InterviewSession.created_at,
            User.full_name,
        )
        .join(User, User.id == InterviewSession.user_id)
        .order_by(InterviewSession.created_at.desc())
        .limit(limit)
    ).all()
    for title, job_role, created_at, full_name in sessions:
        events.append(
            AdminActivityEvent(
                event_type="session_created",
                title=f"{full_name} started an interview",
                subtitle=f"{title} — {job_role}",
                created_at=created_at,
            )
        )

    reports = db.execute(
        select(SessionReport.created_at, InterviewSession.title, User.full_name)
        .join(InterviewSession, SessionReport.session_id == InterviewSession.id)
        .join(User, User.id == InterviewSession.user_id)
        .order_by(SessionReport.created_at.desc())
        .limit(limit)
    ).all()
    for created_at, title, full_name in reports:
        events.append(
            AdminActivityEvent(
                event_type="report_generated",
                title=f"AI report generated for {full_name}",
                subtitle=title,
                created_at=created_at,
            )
        )

    resumes = db.execute(
        select(ResumeDocument.created_at, ResumeDocument.filename, User.full_name)
        .join(User, User.id == ResumeDocument.user_id)
        .order_by(ResumeDocument.created_at.desc())
        .limit(limit)
    ).all()
    for created_at, filename, full_name in resumes:
        events.append(
            AdminActivityEvent(
                event_type="resume_uploaded",
                title=f"{full_name} uploaded a resume",
                subtitle=filename,
                created_at=created_at,
            )
        )

    events.sort(key=lambda e: _as_aware_utc(e.created_at), reverse=True)
    return events[:limit]
