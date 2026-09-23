from __future__ import annotations

import time
import uuid
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.exceptions import ResourceNotFound
from app.models.conversation import (
    ConversationTurn,
    ConversationTurnAnalysis,
    LiveInterviewSession,
)
from app.models.interview import (
    InterviewSession,
    SESSION_STATUS_COMPLETED,
    SESSION_STATUS_DRAFT,
)
from app.schemas.interview import SessionCreate, SessionUpdate
from app.services import evaluation_service

# Bounded retry for mirror_completed_live_session's insert, against a
# transient dropped/stale DB connection specifically (OperationalError) —
# e.g. Neon's pooler closing an idle connection between pool_pre_ping's
# check and this statement. Without this, that one-off blip permanently
# and silently hides an otherwise-successfully-completed live interview
# from /interviews, the dashboard, readiness, and coaching forever: once
# end_interview sets status=COMPLETED, a second /end call 409s immediately
# and never reaches the mirror step again — there is no other retry path.
# Deliberately small: this runs synchronously inside the candidate's
# end-interview request, so it must add ~nothing to the common (no
# failure) case and only a few hundred ms even in the worst case.
_MIRROR_MAX_ATTEMPTS = 3
_MIRROR_RETRY_DELAY_SECONDS = 0.2


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


def mirror_completed_live_session(
    db: Session,
    live_session: LiveInterviewSession,
) -> InterviewSession:
    """Create (or return the existing) InterviewSession mirroring a completed
    LiveInterviewSession, so it appears in GET /interviews and dashboard
    analytics — both read interview_sessions exclusively and have no
    knowledge of live_interview_sessions.

    Idempotent by construction:
      - Checked first: an InterviewSession already mirroring this
        live_session (matched by live_session_id) is returned as-is rather
        than duplicated — the common case for a backfill re-run.
      - Enforced under a race: uq_interview_sessions_live_session_id makes a
        concurrent double-insert raise IntegrityError, which is caught here
        and resolved by returning the row the other call just committed.

    Retried up to _MIRROR_MAX_ATTEMPTS times on OperationalError (a
    transient dropped/stale connection) — see the module-level comment
    above these constants for why this is worth a bounded retry
    specifically for this call, unlike most single-shot writes elsewhere.

    title has no equivalent field on LiveInterviewSession and is
    synthesized. created_at is copied from the live session (rather than
    left to default to "now") so the mirrored session's history reflects
    when the interview actually happened, not when it was mirrored.

    Callers decide how to handle failure — see live_interview.end_interview,
    which logs and continues rather than failing an otherwise-successful
    interview completion.
    """
    existing = (
        db.query(InterviewSession)
        .filter(InterviewSession.live_session_id == live_session.id)
        .first()
    )
    if existing is not None:
        return existing

    last_exc: OperationalError | None = None
    for attempt in range(1, _MIRROR_MAX_ATTEMPTS + 1):
        mirrored = InterviewSession(
            user_id=live_session.user_id,
            title=f"Live Interview – {live_session.job_role}",
            job_role=live_session.job_role,
            job_description=live_session.job_description,
            status=SESSION_STATUS_COMPLETED,
            created_at=live_session.created_at,
            live_session_id=live_session.id,
        )
        db.add(mirrored)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            existing = (
                db.query(InterviewSession)
                .filter(InterviewSession.live_session_id == live_session.id)
                .first()
            )
            if existing is None:
                raise
            return existing
        except OperationalError as exc:
            db.rollback()
            last_exc = exc
            if attempt < _MIRROR_MAX_ATTEMPTS:
                time.sleep(_MIRROR_RETRY_DELAY_SECONDS)
            continue
        else:
            db.refresh(mirrored)
            return mirrored

    assert last_exc is not None  # loop always sets it before falling through
    raise last_exc


def score_and_store_conversation_turn(
    db: Session,
    turn: ConversationTurn,
    job_role: str,
    job_description: str,
) -> ConversationTurnAnalysis | None:
    """Score a live-interview answer with Gemini and persist the result.

    The live-interview analogue of processing_service's InterviewAnalysis
    insert — reuses evaluation_service.generate_evaluation() unmodified
    (it only ever needed plain question/answer/role text, never an
    AudioResponse) and converts scores via Decimal(str(v)) exactly like
    processing_service does, for the same reason: Decimal(v) on a raw
    float would inherit IEEE 754 imprecision (e.g. Decimal("7.4999999...")
    instead of Decimal("7.5")).

    Returns None, without calling Gemini, when there is nothing to score
    (response_text is None or blank) — a turn with no answer simply gets
    no analysis row, the same way an unanswered Question in the upload
    flow simply has no AudioResponse.

    Idempotent: checked first (the common case — e.g. a caller re-scoring
    an already-scored turn), and enforced under a race by
    uq_conversation_turn_analyses_turn_id, exactly like
    mirror_completed_live_session's IntegrityError fallback.

    Raises whatever evaluation_service.generate_evaluation() raises
    (AIServiceError) — this function does not swallow Gemini failures.
    Callers that must not let scoring block their own success (see
    live_interview.next_question) are responsible for catching it.
    """
    if not turn.response_text or not turn.response_text.strip():
        return None

    existing = (
        db.query(ConversationTurnAnalysis)
        .filter(ConversationTurnAnalysis.conversation_turn_id == turn.id)
        .first()
    )
    if existing is not None:
        return existing

    evaluation_result = evaluation_service.generate_evaluation(
        transcript_text=turn.response_text,
        question=turn.question_text,
        job_role=job_role,
        job_description=job_description,
    )

    analysis = ConversationTurnAnalysis(
        conversation_turn_id=turn.id,
        overall_score=Decimal(str(evaluation_result["overall_score"])),
        communication_score=Decimal(str(evaluation_result["communication_score"])),
        technical_score=Decimal(str(evaluation_result["technical_score"])),
        problem_solving_score=Decimal(
            str(evaluation_result["problem_solving_score"])
        ),
        confidence_score=Decimal(str(evaluation_result["confidence_score"])),
        strengths=evaluation_result["strengths"],
        weaknesses=evaluation_result["weaknesses"],
        detailed_feedback=evaluation_result["detailed_feedback"],
        model_used=evaluation_result["model_used"],
    )
    db.add(analysis)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(ConversationTurnAnalysis)
            .filter(ConversationTurnAnalysis.conversation_turn_id == turn.id)
            .first()
        )
        if existing is None:
            raise
        return existing

    db.refresh(analysis)
    return analysis


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
