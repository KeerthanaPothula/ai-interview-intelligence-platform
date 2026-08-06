"""Aggregation service for the admin dashboard.

Gated behind app.core.permissions.can_view_platform /
can_manage_users / can_manage_organizations (Admin, Super Admin — never
Recruiter or Candidate). Every read here is platform-wide (every
organization) by design for these two roles — see app.core.permissions'
docstrings for why that's intentional rather than an oversight; contrast
with recruiter_service, which *is* org-scoped for the Recruiter role.
Every number here is a real query against the existing tables; nothing is
mocked or hardcoded.
"""

from __future__ import annotations

import os
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.models.analysis import AudioResponse, InterviewAnalysis, Transcript
from app.models.documents import ResumeDocument
from app.models.features import SessionReport
from app.models.interview import InterviewSession, Question, VALID_SESSION_STATUSES
from app.models.organization import Organization
from app.models.prediction import CoachingPlan, InterviewPrediction
from app.models.role import ROLE_VALUES, Role
from app.models.user import User
from app.schemas.admin import (
    AdminActivityEvent,
    AdminOverviewResponse,
    AdminUserResponse,
    AiUsageStats,
    CreateRecruiterRequest,
    DailyCount,
    JobRoleCount,
    OrganizationResponse,
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
    avg_score_row = db.execute(
        select(func.avg(SessionReport.final_score))
    ).scalar_one_or_none()
    avg_platform_score = (
        round(float(avg_score_row), 2) if avg_score_row is not None else None
    )

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
    recent_signups = (
        db.execute(select(User.created_at).where(User.created_at >= thirty_days_ago))
        .scalars()
        .all()
    )
    recent_sessions = (
        db.execute(
            select(InterviewSession.created_at).where(
                InterviewSession.created_at >= thirty_days_ago
            )
        )
        .scalars()
        .all()
    )

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
            func.lower(User.full_name).like(needle)
            | func.lower(User.email).like(needle)
        )

    total = db.execute(
        select(func.count()).select_from(base_query.subquery())
    ).scalar_one()

    page = (
        db.execute(
            base_query.order_by(User.created_at.desc()).offset(skip).limit(limit)
        )
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

    org_ids = {u.organization_id for u in page if u.organization_id is not None}
    org_names: dict[uuid.UUID, str] = {}
    if org_ids:
        org_rows = db.execute(
            select(Organization.id, Organization.name).where(
                Organization.id.in_(org_ids)
            )
        ).all()
        org_names = dict(org_rows)

    items = [
        AdminUserResponse(
            id=u.id,
            full_name=u.full_name,
            email=u.email,
            role=u.role,
            organization_id=u.organization_id,
            organization_name=org_names.get(u.organization_id)
            if u.organization_id
            else None,
            is_active=u.is_active,
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


# ---------------------------------------------------------------------------
# Organization management (Phase 9)
# ---------------------------------------------------------------------------


def list_organizations(db: Session) -> tuple[list[OrganizationResponse], int]:
    orgs = db.execute(select(Organization).order_by(Organization.name)).scalars().all()
    if not orgs:
        return [], 0

    org_ids = [o.id for o in orgs]
    member_rows = db.execute(
        select(User.organization_id, User.role, func.count(User.id))
        .where(User.organization_id.in_(org_ids))
        .group_by(User.organization_id, User.role)
    ).all()
    recruiter_counts: dict[uuid.UUID, int] = {}
    candidate_counts: dict[uuid.UUID, int] = {}
    for org_id, role, count in member_rows:
        if role == Role.RECRUITER.value:
            recruiter_counts[org_id] = count
        elif role == Role.CANDIDATE.value:
            candidate_counts[org_id] = count

    items = [
        OrganizationResponse(
            id=o.id,
            name=o.name,
            is_active=o.is_active,
            created_at=o.created_at,
            recruiter_count=recruiter_counts.get(o.id, 0),
            candidate_count=candidate_counts.get(o.id, 0),
        )
        for o in orgs
    ]
    return items, len(items)


def create_organization(db: Session, *, name: str) -> Organization:
    stripped = name.strip()
    existing = db.execute(
        select(Organization).where(func.lower(Organization.name) == stripped.lower())
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An organization with this name already exists.",
        )
    org = Organization(name=stripped)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def set_organization_active(
    db: Session, *, org_id: uuid.UUID, is_active: bool
) -> Organization:
    org = db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Organization not found.")
    org.is_active = is_active
    db.commit()
    db.refresh(org)
    return org


# ---------------------------------------------------------------------------
# Recruiter provisioning (Phase 9)
# ---------------------------------------------------------------------------


def create_recruiter(db: Session, data: CreateRecruiterRequest) -> User:
    """Admin-provisioned recruiter account — the only way a RECRUITER role
    is ever assigned at creation time (self-registration always assigns
    CANDIDATE; see app.services.auth_service.register_user)."""
    org = db.get(Organization, data.organization_id)
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Organization not found.")

    existing = db.execute(
        select(User).where(func.lower(User.email) == data.email.lower())
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    recruiter = User(
        email=data.email,
        hashed_password=get_password_hash(data.password),
        full_name=data.full_name,
        role=Role.RECRUITER.value,
        organization_id=data.organization_id,
    )
    db.add(recruiter)
    db.commit()
    db.refresh(recruiter)
    return recruiter


# ---------------------------------------------------------------------------
# User activation and role assignment (Phase 2 / Phase 9)
# ---------------------------------------------------------------------------


def set_user_active(
    db: Session, *, user_id: uuid.UUID, is_active: bool, acting_user: User
) -> User:
    if user_id == acting_user.id and not is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate your own account.",
        )
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found.")
    user.is_active = is_active
    db.commit()
    db.refresh(user)
    return user


def set_user_role(
    db: Session, *, user_id: uuid.UUID, new_role: str, acting_user: User
) -> User:
    """Super-Admin-only (enforced by the router's can_assign_roles gate,
    not re-checked here — this function trusts its caller like every other
    service function in this codebase)."""
    if new_role not in ROLE_VALUES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid role. Must be one of: {', '.join(sorted(ROLE_VALUES))}.",
        )
    if user_id == acting_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot change your own role.",
        )
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found.")

    user.role = new_role
    # Force re-login: any access token already issued for this user still
    # carries the *old* role in its (informational-only, never-trusted)
    # claim, and — more importantly — get_current_user re-checks the DB
    # row on every request anyway, so this isn't required for the
    # authorization decision itself. It's still bumped for the same
    # belt-and-suspenders reason password changes bump it: a stale token
    # should stop working the moment a security-relevant attribute changes.
    user.token_version = (user.token_version or 0) + 1
    db.commit()
    db.refresh(user)
    return user
