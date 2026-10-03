"""Live Conversational AI Interviewer — multi-turn interview endpoints."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.constants import API_V1_PREFIX
from app.core.rate_limit import enforce_ai_rate_limit
from app.core.exceptions import ResourceNotFound
from app.database import get_db
from app.models.analysis import AudioResponse
from app.models.conversation import (
    LIVE_SESSION_STATUS_ACTIVE,
    LIVE_SESSION_STATUS_COMPLETED,
    ConversationTurn,
    LiveInterviewSession,
)
from app.core.permissions import can_create_interview
from app.routers.auth import get_current_user
from app.schemas.conversation import (
    EndInterviewRequest,
    EndInterviewResponse,
    LiveInterviewSessionResponse,
    NextQuestionRequest,
    StartLiveInterviewRequest,
)
from app.services import interview_conversation_service, interview_service
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix=f"{API_V1_PREFIX}/live-interviews", tags=["Live Interviews"])


def _get_session_or_404(
    session_id: uuid.UUID, user_id: uuid.UUID, db: Session
) -> LiveInterviewSession:
    stmt = (
        select(LiveInterviewSession)
        .where(
            LiveInterviewSession.id == session_id,
            LiveInterviewSession.user_id == user_id,
        )
        .options(selectinload(LiveInterviewSession.turns))
    )
    result = db.execute(stmt).scalar_one_or_none()
    if result is None:
        raise ResourceNotFound("Live interview session not found.")
    return result


def _owned_audio_response_id_or_404(
    db: Session, audio_response_id: uuid.UUID, user_id: uuid.UUID
) -> uuid.UUID:
    """Confirm audio_response_id names an AudioResponse owned by user_id.

    Without this check, a caller could link an arbitrary AudioResponse
    UUID — including one belonging to a different user — into their own
    ConversationTurn: the column's only DB-level constraint is the FK
    (the row must exist), never that the caller owns it. Raises 404
    (never 403) on ownership mismatch or a nonexistent id, matching this
    codebase's established IDOR-avoidance convention (see responses.py,
    follow_up.py) rather than letting a bad id reach db.commit() as an
    unhandled IntegrityError.
    """
    owned = (
        db.query(AudioResponse.id)
        .filter(
            AudioResponse.id == audio_response_id,
            AudioResponse.user_id == user_id,
        )
        .first()
    )
    if owned is None:
        raise ResourceNotFound("Audio response not found.")
    return audio_response_id


def _replay_answered_turn(
    db: Session,
    session: LiveInterviewSession,
    turn_number: int,
    body: NextQuestionRequest,
    current_user: User,
) -> LiveInterviewSessionResponse:
    """Answer a next-question request for a turn that is no longer current.

    Nothing is written or scored. If the request carries the answer already
    stored on that turn (a retry after a lost response), it gets the
    current conversation back, as if it had just succeeded. If it carries a
    different answer, 409 — that answer is never moved onto a newer question.
    """
    turn = db.execute(
        select(ConversationTurn).where(
            ConversationTurn.live_session_id == session.id,
            ConversationTurn.turn_number == turn_number,
        )
    ).scalar_one_or_none()
    if turn is None or turn_number >= session.current_turn:
        raise HTTPException(
            status_code=409,
            detail=f"Question {turn_number} is not the current question.",
        )
    _reject_different_answer(turn, body)
    return get_conversation(session.id, db, current_user)


def _save_first_answer(
    db: Session,
    turn: ConversationTurn,
    body: NextQuestionRequest | EndInterviewRequest,
    user_id: uuid.UUID,
) -> None:
    """Save body's answer on turn unless one is already saved; 409 if the
    saved answer differs from body's.

    First accepted answer wins: one conditional UPDATE claims the turn only
    while it is still unanswered, so of two concurrent requests exactly one
    writes (the other's UPDATE waits on the row lock, then matches nothing).
    Everyone then re-reads what was persisted: the same answer carries on as
    a retry, a different one gets 409 and is never scored. Committed here,
    before any best-effort scoring, so a scoring rollback can never discard
    the saved answer. Afterwards `turn` holds exactly the persisted answer.
    """
    audio_id = (
        _owned_audio_response_id_or_404(db, body.audio_response_id, user_id)
        if body.audio_response_id
        else None
    )
    db.execute(
        update(ConversationTurn)
        .where(
            ConversationTurn.id == turn.id,
            ConversationTurn.response_text.is_(None),
            ConversationTurn.audio_response_id.is_(None),
        )
        .values(response_text=body.response_text, audio_response_id=audio_id)
        .execution_options(synchronize_session=False)
    )
    db.commit()
    db.refresh(turn)
    _reject_different_answer(turn, body)


def _reject_different_answer(
    turn: ConversationTurn, body: NextQuestionRequest | EndInterviewRequest
) -> None:
    """409 if body carries an answer other than the one saved on turn.

    The first saved answer is authoritative: a request repeating it (or
    sending none) is a retry, anything else must not replace it.
    """
    if (body.response_text and body.response_text != turn.response_text) or (
        body.audio_response_id and body.audio_response_id != turn.audio_response_id
    ):
        raise HTTPException(
            status_code=409,
            detail=f"Question {turn.turn_number} already has a different saved "
            "answer, so this answer was not saved.",
        )


@router.post(
    "/",
    response_model=LiveInterviewSessionResponse,
    status_code=201,
    dependencies=[Depends(enforce_ai_rate_limit)],
)
def start_live_interview(
    body: StartLiveInterviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(can_create_interview()),
):
    """Start a new live interview session and receive the first question."""
    first_question = interview_conversation_service.generate_opening_question(
        job_role=body.job_role,
        job_description=body.job_description,
    )

    session = LiveInterviewSession(
        user_id=current_user.id,
        job_role=body.job_role,
        job_description=body.job_description,
        max_turns=body.max_turns,
        current_turn=1,
        status=LIVE_SESSION_STATUS_ACTIVE,
    )
    db.add(session)
    db.flush()

    turn = ConversationTurn(
        live_session_id=session.id,
        turn_number=1,
        question_text=first_question,
        difficulty_level=1,
    )
    db.add(turn)
    db.commit()
    db.refresh(session)

    turns = (
        db.execute(
            select(ConversationTurn)
            .where(ConversationTurn.live_session_id == session.id)
            .order_by(ConversationTurn.turn_number)
        )
        .scalars()
        .all()
    )

    data = LiveInterviewSessionResponse.model_validate(session)
    data.turns = [t for t in turns]
    data.current_question = turns[-1] if turns else None
    return data


@router.post(
    "/{session_id}/next-question",
    response_model=LiveInterviewSessionResponse,
    dependencies=[Depends(enforce_ai_rate_limit)],
)
def next_question(
    session_id: uuid.UUID,
    body: NextQuestionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Record the candidate's response to the current question and get the next one."""
    session = _get_session_or_404(session_id, current_user.id, db)

    if session.status == LIVE_SESSION_STATUS_COMPLETED:
        raise HTTPException(
            status_code=409, detail="Interview session is already completed"
        )

    # Checked before the max_turns guard: a retry whose original request
    # created the final turn (but whose response was lost) must still replay.
    answered_turn = session.current_turn
    if body.turn_number is not None and body.turn_number != answered_turn:
        return _replay_answered_turn(db, session, body.turn_number, body, current_user)

    if session.current_turn >= session.max_turns:
        raise HTTPException(
            status_code=409,
            detail="All questions have been asked. Call end-interview to finish.",
        )

    # Save response to the current (last) turn
    current_turns = (
        db.execute(
            select(ConversationTurn)
            .where(ConversationTurn.live_session_id == session.id)
            .order_by(ConversationTurn.turn_number)
        )
        .scalars()
        .all()
    )

    if current_turns and (body.response_text or body.audio_response_id):
        last_turn = current_turns[-1]
        # A same-answer retry carries on, which still lets a retry after
        # failed question generation advance.
        _save_first_answer(db, last_turn, body, current_user.id)

        # Score the answer just submitted so Readiness Assessment and
        # Coaching Plan have genuine per-turn data to average later (see
        # prediction.py's live-session branch). Best-effort: a candidate
        # must always get their next question even if Gemini scoring is
        # slow, rate-limited, or fails outright — this must never turn a
        # successful next-question response into an error.
        try:
            interview_service.score_and_store_conversation_turn(
                db, last_turn, session.job_role, session.job_description
            )
        except Exception:
            logger.exception(
                "Failed to score conversation turn %s for live session %s; "
                "next-question generation continues unaffected.",
                last_turn.id,
                session.id,
            )
            db.rollback()

    history = [
        {
            "turn_number": t.turn_number,
            "question_text": t.question_text,
            "response_text": t.response_text,
        }
        for t in current_turns
    ]

    next_q_text, difficulty = (
        interview_conversation_service.generate_follow_up_question(
            job_role=session.job_role,
            job_description=session.job_description,
            conversation_history=history,
            current_turn=session.current_turn,
            max_turns=session.max_turns,
        )
    )

    new_turn_number = session.current_turn + 1
    new_turn = ConversationTurn(
        live_session_id=session.id,
        turn_number=new_turn_number,
        question_text=next_q_text,
        difficulty_level=difficulty,
    )
    db.add(new_turn)
    session.current_turn = new_turn_number
    try:
        db.commit()
    except IntegrityError:
        # uq_conversation_turns_session_turn: a concurrent request for the
        # same turn created the next one first. Answer as a retry would.
        db.rollback()
        db.refresh(session)
        if session.current_turn == answered_turn:
            raise
        return _replay_answered_turn(db, session, answered_turn, body, current_user)

    all_turns = (
        db.execute(
            select(ConversationTurn)
            .where(ConversationTurn.live_session_id == session.id)
            .order_by(ConversationTurn.turn_number)
        )
        .scalars()
        .all()
    )

    data = LiveInterviewSessionResponse.model_validate(session)
    data.turns = list(all_turns)
    data.current_question = all_turns[-1] if all_turns else None
    return data


@router.get("/{session_id}/conversation", response_model=LiveInterviewSessionResponse)
def get_conversation(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the full conversation history for a live interview session."""
    session = _get_session_or_404(session_id, current_user.id, db)

    turns = (
        db.execute(
            select(ConversationTurn)
            .where(ConversationTurn.live_session_id == session.id)
            .order_by(ConversationTurn.turn_number)
        )
        .scalars()
        .all()
    )

    data = LiveInterviewSessionResponse.model_validate(session)
    data.turns = list(turns)
    data.current_question = turns[-1] if turns else None
    return data


@router.get("/active", response_model=LiveInterviewSessionResponse | None)
def get_active_interview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The caller's most recent still-active live interview, or null.

    The client only learns a session id from the start response, so after a
    refresh or navigating away it has no other way to find an interview in
    progress. Read-only: never creates turns and never completes anything.
    """
    session_id = db.execute(
        select(LiveInterviewSession.id)
        .where(
            LiveInterviewSession.user_id == current_user.id,
            LiveInterviewSession.status == LIVE_SESSION_STATUS_ACTIVE,
        )
        .order_by(LiveInterviewSession.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if session_id is None:
        return None
    return get_conversation(session_id, db, current_user)


@router.post(
    "/{session_id}/end",
    response_model=EndInterviewResponse,
    dependencies=[Depends(enforce_ai_rate_limit)],
)
def end_interview(
    session_id: uuid.UUID,
    # Defaulted (not just Optional) so a client that sends no body at all —
    # including the pre-fix frontend build, during a rolling deploy — keeps
    # working exactly as before: ending without an answer to the final
    # question. FastAPI only validates a real body when one is sent.
    body: EndInterviewRequest = EndInterviewRequest(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """End the live interview session and get a summary."""
    session = _get_session_or_404(session_id, current_user.id, db)

    if session.status == LIVE_SESSION_STATUS_COMPLETED:
        raise HTTPException(
            status_code=409, detail="Interview session is already completed"
        )

    turns = (
        db.execute(
            select(ConversationTurn)
            .where(ConversationTurn.live_session_id == session.id)
            .order_by(ConversationTurn.turn_number)
        )
        .scalars()
        .all()
    )

    # Persist and score the final answer — mirrors next_question's exact
    # pattern, because end_interview is the ONLY place the last question's
    # answer can ever be submitted (the frontend hides next-question once
    # the candidate reaches the final turn). turns[-1] is refreshed to the
    # persisted answer, so the history built below (for the summary) and
    # the turns returned in the response both reflect it — no re-query.
    if turns and (body.response_text or body.audio_response_id):
        last_turn = turns[-1]
        _save_first_answer(db, last_turn, body, current_user.id)

        try:
            interview_service.score_and_store_conversation_turn(
                db, last_turn, session.job_role, session.job_description
            )
        except Exception:
            logger.exception(
                "Failed to score final conversation turn %s for live "
                "session %s; interview completion continues unaffected.",
                last_turn.id,
                session.id,
            )
            db.rollback()

    history = [
        {
            "turn_number": t.turn_number,
            "question_text": t.question_text,
            "response_text": t.response_text,
        }
        for t in turns
    ]

    summary = interview_conversation_service.generate_interview_summary(
        job_role=session.job_role,
        conversation_history=history,
    )

    # Conditional, like the answer: if a concurrent End (with the same
    # answer — a different one got 409 above) completed it first, its
    # completion stands and this request still succeeds idempotently.
    db.execute(
        update(LiveInterviewSession)
        .where(
            LiveInterviewSession.id == session.id,
            LiveInterviewSession.status == LIVE_SESSION_STATUS_ACTIVE,
        )
        .values(
            status=LIVE_SESSION_STATUS_COMPLETED,
            completed_at=datetime.now(timezone.utc),
        )
        .execution_options(synchronize_session=False)
    )
    db.commit()
    db.refresh(session)

    # Built now, from data already loaded, so the response the candidate
    # sees does not depend on what happens to the DB session below — a
    # rollback there must not be able to expire and re-fetch (or fail to
    # re-fetch) objects this response already needs.
    response = EndInterviewResponse(
        session_id=session.id,
        status=LIVE_SESSION_STATUS_COMPLETED,
        total_turns=len(turns),
        summary=summary,
        turns=list(turns),
    )

    # Mirror into interview_sessions so this interview appears in
    # GET /interviews and dashboard analytics (both are blind to
    # live_interview_sessions). The live interview above is already
    # committed and successful at this point — a failure here must not
    # turn that success into a 500, so it is logged and swallowed rather
    # than raised. db.rollback() discards only the failed mirror insert;
    # it cannot undo the session.status commit that already happened.
    try:
        interview_service.mirror_completed_live_session(db, session)
    except Exception:
        logger.exception(
            "Failed to mirror completed live interview session %s into "
            "interview_sessions; the live interview itself completed "
            "successfully and is unaffected.",
            session.id,
        )
        db.rollback()

    return response
