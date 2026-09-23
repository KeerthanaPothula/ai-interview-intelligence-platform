"""Live Conversational AI Interviewer — multi-turn interview endpoints."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.constants import API_V1_PREFIX
from app.core.exceptions import ResourceNotFound
from app.database import get_db
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


@router.post("/", response_model=LiveInterviewSessionResponse, status_code=201)
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


@router.post("/{session_id}/next-question", response_model=LiveInterviewSessionResponse)
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
        if body.response_text:
            last_turn.response_text = body.response_text
        if body.audio_response_id:
            last_turn.audio_response_id = body.audio_response_id

        # Committed now, before the best-effort scoring attempt below —
        # autoflush is off for this Session, so an uncommitted
        # response_text is only a pending in-memory change. If scoring
        # then fails and we roll back, that rollback must discard only the
        # failed scoring attempt, never the candidate's answer.
        db.commit()

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
    db.commit()

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


@router.post("/{session_id}/end", response_model=EndInterviewResponse)
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
    # the candidate reaches the final turn). Mutating turns[-1] here means
    # the history built below (for the summary) and the turns returned in
    # the response both automatically reflect it — no re-query needed.
    if turns and (body.response_text or body.audio_response_id):
        last_turn = turns[-1]
        if body.response_text:
            last_turn.response_text = body.response_text
        if body.audio_response_id:
            last_turn.audio_response_id = body.audio_response_id

        # Committed before the best-effort scoring attempt below, for the
        # same reason as next_question: a scoring failure's rollback must
        # discard only the failed scoring attempt, never this answer.
        db.commit()

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

    session.status = LIVE_SESSION_STATUS_COMPLETED
    session.completed_at = datetime.now(timezone.utc)
    db.commit()

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
