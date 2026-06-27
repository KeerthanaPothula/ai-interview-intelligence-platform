from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.exceptions import ResourceNotFound
from app.models.interview import (
    InterviewSession,
    SESSION_STATUS_DRAFT,
)
from app.schemas.interview import SessionCreate, SessionUpdate


def create_session(
    db: Session,
    user_id: uuid.UUID,
    data: SessionCreate,
) -> InterviewSession:
    """Insert a new InterviewSession row owned by user_id.

    Status defaults to SESSION_STATUS_DRAFT via the ORM model default.
    commit() + refresh() ensures the caller receives the server-generated
    created_at, updated_at, and id values.
    """
    session = InterviewSession(
        user_id=user_id,
        title=data.title,
        job_role=data.job_role,
        job_description=data.job_description,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_session_or_404(
    db: Session,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
) -> InterviewSession:
    """Return the session if it exists and belongs to user_id.

    Raises HTTP 404 in both of these cases:
      - session_id does not exist in the database
      - session_id exists but belongs to a different user

    HTTP 403 is intentionally never raised here. Returning 403 would
    confirm to a probing attacker that the session exists. HTTP 404 gives
    no information: the session either doesn't exist or doesn't belong to
    the caller — they cannot tell which.

    This function is the single security boundary for session ownership.
    All routers that operate on a specific session must call this first.
    """
    session = (
        db.query(InterviewSession)
        .filter(
            InterviewSession.id == session_id,
            InterviewSession.user_id == user_id,
        )
        .first()
    )
    if session is None:
        raise ResourceNotFound("Session not found.")
    return session


def list_sessions(
    db: Session,
    user_id: uuid.UUID,
    skip: int = 0,
    limit: int = 20,
) -> list[InterviewSession]:
    """Return a page of sessions belonging to user_id, newest first.

    Ordered by created_at DESC so the most recent sessions appear at the
    top of the list. skip/limit implement cursor-free pagination.
    User isolation is enforced by the WHERE user_id = ? filter — the
    caller never sees sessions belonging to other users.
    """
    return (
        db.query(InterviewSession)
        .filter(InterviewSession.user_id == user_id)
        .order_by(InterviewSession.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def update_session(
    db: Session,
    session: InterviewSession,
    data: SessionUpdate,
) -> InterviewSession:
    """Apply a partial update to session and persist the change.

    Status gate: only sessions in 'draft' status may be modified.
    Once a session moves to 'in_progress', 'processing', or 'completed',
    its metadata is locked. HTTP 409 is raised for any other status.

    PATCH semantics via model_fields_set: only fields explicitly included
    in the client's request body are updated. A field absent from the
    JSON body has a Python default of None, but is NOT in model_fields_set.
    Without this check, every PATCH would overwrite unspecified fields with
    None, silently clearing data the client did not intend to change.

    commit() + refresh() reloads the row to return the updated updated_at
    timestamp (set by the ORM's onupdate=func.now() on InterviewSession).
    """
    if session.status != SESSION_STATUS_DRAFT:
        raise HTTPException(
            status_code=409,
            detail="Session can only be modified while in draft status.",
        )

    updatable_fields = {"title", "job_role", "job_description"}
    for field in data.model_fields_set & updatable_fields:
        setattr(session, field, getattr(data, field))

    db.commit()
    db.refresh(session)
    return session


def delete_session(
    db: Session,
    session: InterviewSession,
) -> None:
    """Delete the session and all its owned rows via ORM cascade.

    Uses db.delete(session) rather than a bulk query-level DELETE.

    Why the distinction matters:
      InterviewSession.questions has cascade="all, delete-orphan". When
      db.delete(session) is called, SQLAlchemy walks the loaded ORM
      relationships and marks Question objects for deletion in the identity
      map — this fires the ORM cascade correctly.

      A db.query(InterviewSession).filter(...).delete() call issues a raw
      SQL DELETE that bypasses the ORM identity map entirely. Any Question
      or AudioResponse objects already loaded in the session would become
      silently stale (DB rows gone, ORM objects still present in memory),
      corrupting the unit of work.

    Cascade chain:
      session deleted (ORM) →
        questions cascade="all, delete-orphan" (ORM) →
          audio_responses ON DELETE CASCADE on question_id (DB) via passive_deletes=True
      session deleted (ORM) →
        audio_responses ON DELETE CASCADE on session_id (DB) via passive_deletes=True

    No refresh is needed after delete — the session object is expunged
    from the identity map and should not be used after this call.
    """
    db.delete(session)
    db.commit()
