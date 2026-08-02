"""Aggregation service for the recruiter dashboard.

The User model has no role/organisation concept (see its docstring) — this
is a single-tenant MVP schema. Rather than bolt on a role system, the
recruiter dashboard treats every user's latest *completed* interview as a
"candidate" row and is reachable by any authenticated user, matching the
route's existing (pre-this-change) access model. That is an acceptable
trade-off for a demo/portfolio app seeded with fake accounts; a real
multi-tenant deployment would need a recruiter role gate before this
became appropriate.

Sorting and filtering happen in Python after two small aggregate queries
rather than one large SQL query with computed ORDER BY, because the score
columns are themselves aggregates (AVG across a session's responses) and
per-candidate resume scores are a heuristic computed from resume text that
isn't stored anywhere. At this app's scale (one row per registered user)
that's a non-issue; it would need to move into SQL if the user base grew
into the tens of thousands.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.documents import ResumeDocument
from app.models.features import SessionReport
from app.models.interview import SESSION_STATUS_COMPLETED, InterviewSession
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
VALID_STATUSES = {"shortlisted", "reviewing", "pending", "rejected"}


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


def _status_for_score(score: int) -> str:
    if score >= 85:
        return "shortlisted"
    if score >= 70:
        return "reviewing"
    if score >= 55:
        return "pending"
    return "rejected"


def _all_candidates(db: Session) -> list[Candidate]:
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

    rows = db.execute(
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
    ).all()

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
        resume_score = estimate_ats_score(len(resume_text.split())) if resume_text else None
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
                status=_status_for_score(interview_score),
                applied_days=applied_days,
            )
        )
    return candidates


def list_candidates(
    db: Session,
    *,
    search: str | None = None,
    status: str | None = None,
    sort_by: str = "interviewScore",
    sort_dir: str = "desc",
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[Candidate], int, dict[str, float | int | None]]:
    """Return a page of candidates, the total match count, and summary stats.

    Summary stats (avg scores, shortlisted count) are computed over the
    full filtered set, not just the returned page.
    """
    candidates = _all_candidates(db)

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
        "avg_resume_score": round(sum(resume_scores) / len(resume_scores), 1) if resume_scores else None,
        "avg_interview_score": (
            round(sum(c.interview_score for c in candidates) / total, 1) if total else None
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
