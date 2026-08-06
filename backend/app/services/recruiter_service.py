"""Aggregation service for the recruiter dashboard.

Multi-tenant scoping: a Recruiter only ever sees candidates whose
User.organization_id matches their own organization — see
_scope_organization_id and its use in _all_candidates. Admin/Super Admin
pass organization_id=None and see every organization's candidates
unscoped. The router's role gate (can_view_candidates in
app.core.permissions) guarantees only these three roles reach this module
at all — a Candidate can never call list_candidates.

Lifecycle: a session becomes a "candidate" row only once it has reached
SESSION_STATUS_COMPLETED *and* has a SessionReport (see the INNER JOIN on
SessionReport in _all_candidates) — an in-progress or draft interview never
appears here, satisfying the
"Creates Interview -> Completes -> Evaluation -> Report -> Recruiter can
view" lifecycle by construction, not by an extra filter bolted on top.

Sorting and filtering happen in Python after two small aggregate queries
rather than one large SQL query with computed ORDER BY, because the score
columns are themselves aggregates (AVG across a session's responses) and
per-candidate resume scores are a heuristic computed from resume text that
isn't stored anywhere. At this app's scale (one row per organization member)
that's a non-issue; it would need to move into SQL if any single
organization's headcount grew into the tens of thousands.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.documents import ResumeDocument
from app.models.features import SessionReport
from app.models.interview import (
    RECRUITER_STATUS_APPLIED,
    SESSION_STATUS_COMPLETED,
    VALID_RECRUITER_STATUSES,
    InterviewSession,
)
from app.models.role import Role
from app.models.user import User
from app.services.resume_scoring import estimate_ats_score

VALID_SORT_KEYS = {
    "name",
    "resumeScore",
    "interviewScore",
    "communication",
    "technical",
    "appliedDays",
}
VALID_STATUSES = VALID_RECRUITER_STATUSES


@dataclass(frozen=True)
class Candidate:
    id: uuid.UUID
    session_id: uuid.UUID
    name: str
    email: str
    role: str
    resume_score: int | None
    interview_score: int
    communication: int
    technical: int
    sessions_completed: int
    status: str
    applied_days: int


def _as_aware_utc(dt: datetime) -> datetime:
    """SQLite (tests) can round-trip DateTime(timezone=True) values as naive."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def scope_organization_id(current_user: User) -> uuid.UUID | None:
    """Return the organization_id to scope candidate queries to, or None
    for "no scoping" (platform-wide — Admin/Super Admin only).

    A Recruiter with organization_id=None (should never happen in practice
    — Admin-created recruiter accounts always assign one — but defensively
    handled) sees zero candidates rather than the whole platform: falling
    open on a misconfigured account would be the actual security bug here.
    """
    if current_user.role in (Role.ADMIN.value, Role.SUPER_ADMIN.value):
        return None
    return current_user.organization_id


def _all_candidates(
    db: Session, *, organization_id: uuid.UUID | None
) -> list[Candidate]:
    # ROW_NUMBER() rather than a self-join on MAX(created_at): sessions
    # created within the same wall-clock second (SQLite's DateTime
    # resolution, exercised by tests that create two sessions back-to-back)
    # would otherwise tie on created_at and the equality join would match
    # both rows instead of exactly one. id DESC breaks ties deterministically.
    row_number_expr = (
        func.row_number()
        .over(
            partition_by=InterviewSession.user_id,
            order_by=(InterviewSession.created_at.desc(), InterviewSession.id.desc()),
        )
        .label("rn")
    )
    latest_session_subq = (
        select(InterviewSession.id.label("session_id"), row_number_expr)
        .join(SessionReport, SessionReport.session_id == InterviewSession.id)
        .where(InterviewSession.status == SESSION_STATUS_COMPLETED)
        .subquery()
    )
    sessions_completed_subq = (
        select(
            InterviewSession.user_id.label("user_id"),
            func.count(InterviewSession.id).label("sessions_completed"),
        )
        .where(InterviewSession.status == SESSION_STATUS_COMPLETED)
        .group_by(InterviewSession.user_id)
        .subquery()
    )

    query = (
        select(
            InterviewSession,
            SessionReport,
            User,
            sessions_completed_subq.c.sessions_completed,
        )
        .join(SessionReport, SessionReport.session_id == InterviewSession.id)
        .join(User, User.id == InterviewSession.user_id)
        .join(
            latest_session_subq,
            (latest_session_subq.c.session_id == InterviewSession.id)
            & (latest_session_subq.c.rn == 1),
        )
        .join(
            sessions_completed_subq,
            sessions_completed_subq.c.user_id == InterviewSession.user_id,
        )
    )
    if organization_id is not None:
        query = query.where(User.organization_id == organization_id)

    rows = db.execute(query).all()

    if not rows:
        return []

    user_ids = [user.id for _, _, user, _ in rows]

    resume_rows = db.execute(
        select(
            ResumeDocument.user_id,
            ResumeDocument.extracted_text,
            ResumeDocument.created_at,
        )
        .where(ResumeDocument.user_id.in_(user_ids))
        .order_by(ResumeDocument.user_id, ResumeDocument.created_at.desc())
    ).all()
    latest_resume_text: dict[uuid.UUID, str] = {}
    for row in resume_rows:
        if row.user_id not in latest_resume_text:
            latest_resume_text[row.user_id] = row.extracted_text or ""

    now = datetime.now(timezone.utc)
    candidates: list[Candidate] = []
    for session, report, user, sessions_completed in rows:
        interview_score = round(float(report.final_score or 0) * 10)
        resume_text = latest_resume_text.get(user.id)
        resume_score = (
            estimate_ats_score(len(resume_text.split())) if resume_text else None
        )
        applied_days = max(0, (now - _as_aware_utc(session.created_at)).days)
        candidates.append(
            Candidate(
                id=user.id,
                session_id=session.id,
                name=user.full_name,
                email=user.email,
                role=session.job_role,
                resume_score=resume_score,
                interview_score=interview_score,
                communication=round(float(report.communication_score or 0) * 10),
                technical=round(float(report.technical_score or 0) * 10),
                sessions_completed=sessions_completed,
                status=session.recruiter_status or RECRUITER_STATUS_APPLIED,
                applied_days=applied_days,
            )
        )
    return candidates


def list_candidates(
    db: Session,
    *,
    current_user: User,
    search: str | None = None,
    status: str | None = None,
    sort_by: str = "interviewScore",
    sort_dir: str = "desc",
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[Candidate], int, dict[str, float | int | None]]:
    """Return a page of candidates, the total match count, and summary stats.

    Summary stats (avg scores, shortlisted count) are computed over the
    full filtered set, not just the returned page. Scoped to
    current_user's organization unless they're Admin/Super Admin — see
    scope_organization_id.
    """
    candidates = _all_candidates(
        db, organization_id=scope_organization_id(current_user)
    )

    if search:
        needle = search.strip().lower()
        if needle:
            candidates = [
                c
                for c in candidates
                if needle in c.name.lower()
                or needle in c.role.lower()
                or needle in c.email.lower()
            ]

    if status and status in VALID_STATUSES:
        candidates = [c for c in candidates if c.status == status]

    total = len(candidates)
    resume_scores = [c.resume_score for c in candidates if c.resume_score is not None]
    summary: dict[str, float | int | None] = {
        "total_candidates": total,
        "shortlisted_count": sum(1 for c in candidates if c.status == "shortlisted"),
        "avg_resume_score": round(sum(resume_scores) / len(resume_scores), 1)
        if resume_scores
        else None,
        "avg_interview_score": (
            round(sum(c.interview_score for c in candidates) / total, 1)
            if total
            else None
        ),
    }

    sort_key = sort_by if sort_by in VALID_SORT_KEYS else "interviewScore"
    key_fns = {
        "name": lambda c: c.name.lower(),
        "resumeScore": lambda c: c.resume_score if c.resume_score is not None else -1,
        "interviewScore": lambda c: c.interview_score,
        "communication": lambda c: c.communication,
        "technical": lambda c: c.technical,
        "appliedDays": lambda c: c.applied_days,
    }
    candidates.sort(key=key_fns[sort_key], reverse=(sort_dir != "asc"))

    page = candidates[skip : skip + limit]
    return page, total, summary


def update_candidate_status(
    db: Session,
    *,
    session_id: uuid.UUID,
    new_status: str,
    current_user: User,
) -> Candidate:
    """Persist a recruiter-pipeline status change for one candidate's
    latest completed session.

    Raises 422 for an invalid status value, 404 if the session doesn't
    exist, isn't a completed+reported candidate row, or (for a Recruiter)
    belongs to a different organization — 404 rather than 403 for the
    org-mismatch case specifically, so a Recruiter probing session IDs
    outside their organization cannot distinguish "wrong org" from
    "doesn't exist" (the same enumeration-avoidance reasoning already used
    elsewhere in this codebase, e.g. login's "incorrect email or password").
    """
    if new_status not in VALID_RECRUITER_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid status. Must be one of: {', '.join(sorted(VALID_RECRUITER_STATUSES))}.",
        )

    row = db.execute(
        select(InterviewSession, User)
        .join(SessionReport, SessionReport.session_id == InterviewSession.id)
        .join(User, User.id == InterviewSession.user_id)
        .where(
            InterviewSession.id == session_id,
            InterviewSession.status == SESSION_STATUS_COMPLETED,
        )
    ).first()

    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Candidate not found.")

    session, candidate_user = row
    org_scope = scope_organization_id(current_user)
    if org_scope is not None and candidate_user.organization_id != org_scope:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Candidate not found.")

    session.recruiter_status = new_status
    db.commit()
    db.refresh(session)

    updated = [
        c
        for c in _all_candidates(db, organization_id=org_scope)
        if c.session_id == session_id
    ]
    if not updated:
        # Defensive — the row we just updated should always still match
        # the same query that found it above.
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Candidate not found.")
    return updated[0]
