from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.interview import (
    InterviewSession,
    Question,
    SESSION_STATUS_DRAFT,
)
from app.services.gemini_service import generate_questions


def generate_and_save(
    db: Session,
    session: InterviewSession,
) -> list[Question]:
    """Generate interview questions via Gemini and persist them to the DB.

    Operation order (mandatory):
      1. Enforce draft-only gate — reject non-draft sessions immediately.
      2. Call Gemini and validate the response — no DB writes yet.
      3. Bulk-delete existing questions for this session.
      4. Insert new Question ORM objects.
      5. Commit the transaction.
      6. Refresh each new Question to populate server-generated fields.
      7. Return the questions ordered by sequence_order ASC.

    Why Gemini is called before deleting:
      If Gemini fails at step 2 (network error, rate limit, invalid JSON,
      empty result), the existing questions survive. The caller's session
      is left in a valid state — it still has its previous questions.
      Deleting first and then failing would leave the session with zero
      questions and no rollback path for the user experience.

    Why draft-only:
      Once a session moves past 'draft', audio responses have been recorded
      against specific question_id values. Regenerating questions would
      delete those Question rows (via ON DELETE CASCADE on question_id on
      audio_responses), destroying the user's recorded answers. The draft
      gate prevents this.

    Why sequence_order is assigned here (not from Gemini):
      Gemini returns a language model output — it may return duplicate
      sequence numbers, gaps, or no sequence at all. Assigning sequence_order
      as (list index + 1) after parsing guarantees a dense, duplicate-free
      1-based sequence that will never violate the UniqueConstraint on
      (session_id, sequence_order). The 'sequence_order' value inside the
      Gemini-normalized dict is intentionally ignored here.

    Why bulk DELETE instead of ORM individual deletes:
      This is the bulk-delete path that motivated ON DELETE CASCADE on
      audio_responses.question_id. A single SQL DELETE is issued for all
      old questions; the DB cascade cleans up any associated audio_responses
      without the ORM needing to load them. synchronize_session=False skips
      SQLAlchemy's attempt to reconcile the bulk delete with the in-memory
      session.questions collection — safe because we replace the full
      collection immediately afterward.

    Raises:
        HTTPException 409 — session is not in draft status.
        AIServiceError 502 — Gemini is unavailable or returned invalid JSON.
        AIServiceError 429 — Gemini rate limit still exceeded after retries.
    """
    if session.status != SESSION_STATUS_DRAFT:
        raise HTTPException(
            status_code=409,
            detail="Questions can only be generated while the session is in draft status.",
        )

    settings = get_settings()

    # Step 2: Call Gemini. Any failure raises AIServiceError before any DB write.
    question_dicts = generate_questions(
        job_role=session.job_role,
        job_description=session.job_description,
        count=settings.MAX_QUESTIONS_PER_SESSION,
    )

    # Step 3: Bulk-delete all existing questions for this session.
    # ON DELETE CASCADE on audio_responses.question_id handles cleanup of any
    # associated audio response rows at the DB level.
    db.query(Question).filter(Question.session_id == session.id).delete(
        synchronize_session=False
    )

    # Step 4: Insert new Question objects.
    # sequence_order is assigned as (i + 1) — the dict's 'sequence_order'
    # value from gemini_service is intentionally not used here.
    new_questions: list[Question] = []
    for i, q in enumerate(question_dicts):
        question = Question(
            session_id=session.id,
            body=q["body"],
            category=q["category"],
            sequence_order=i + 1,
        )
        db.add(question)
        new_questions.append(question)

    # Step 5: Single commit — delete + insert are atomic.
    #
    # PostgreSQL MVCC note: the bulk DELETE above executed immediately within
    # this transaction. From the perspective of the current connection, the old
    # rows are already gone — subsequent SELECTs in this transaction would not
    # see them. Other concurrent connections still see the pre-DELETE state
    # (MVCC snapshot isolation) until this commit. If commit fails (e.g. a
    # UniqueConstraint violation on a new INSERT), SQLAlchemy rolls back the
    # entire transaction — PostgreSQL undoes both the DELETE and all INSERTs,
    # restoring the pre-call state from every connection's perspective.
    db.commit()

    # Step 6: Refresh to populate server-generated created_at on each row.
    for question in new_questions:
        db.refresh(question)

    # Step 7: Return new_questions directly — already in sequence_order ASC
    # order because sequence_order = i + 1 with a sequential enumerate() loop
    # produces 1, 2, 3, ..., N in insertion order. sorted() would be a no-op.
    return new_questions


def get_questions(
    db: Session,
    session_id: uuid.UUID,
) -> list[Question]:
    """Return all questions for a session, ordered by sequence_order ASC.

    Does not verify ownership — callers must call get_session_or_404 first
    to confirm the session belongs to the authenticated user before calling
    this function.
    """
    return (
        db.query(Question)
        .filter(Question.session_id == session_id)
        .order_by(Question.sequence_order.asc())
        .all()
    )
