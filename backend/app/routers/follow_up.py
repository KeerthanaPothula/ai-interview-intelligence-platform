"""AI Follow-Up Interviewer endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.constants import API_V1_PREFIX
from app.core.deps import get_current_user
from app.core.exceptions import ResourceNotFound
from app.database import get_db
from app.models.analysis import AudioResponse, Transcript
from app.models.features import FollowUpQuestion
from app.models.interview import Question
from app.models.user import User
from app.schemas.features import (
    ConversationTurnResponse,
    FollowUpQuestionResponse,
    FollowUpRequest,
)
from app.services import follow_up_service, interview_service

router = APIRouter(prefix=f"{API_V1_PREFIX}/interviews", tags=["Follow-Up"])


@router.post(
    "/{session_id}/follow-up-question",
    response_model=FollowUpQuestionResponse,
    status_code=status.HTTP_201_CREATED,
)
def generate_follow_up(
    session_id: uuid.UUID,
    body: FollowUpRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FollowUpQuestionResponse:
    """Generate an AI follow-up question based on a candidate's audio response."""
    session = interview_service.get_session_or_404(db, session_id, current_user.id)

    # Validate question belongs to this session.
    question = (
        db.query(Question)
        .filter(
            Question.id == body.question_id,
            Question.session_id == session_id,
        )
        .first()
    )
    if question is None:
        raise ResourceNotFound("Question not found.")

    # Validate audio response belongs to this user and session.
    audio_response = (
        db.query(AudioResponse)
        .filter(
            AudioResponse.id == body.response_id,
            AudioResponse.user_id == current_user.id,
            AudioResponse.session_id == session_id,
        )
        .first()
    )
    if audio_response is None:
        raise ResourceNotFound("Audio response not found.")

    # Load transcript text.
    transcript = (
        db.query(Transcript)
        .filter(Transcript.audio_response_id == body.response_id)
        .first()
    )
    if transcript is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Audio response has not been transcribed yet",
        )

    # Call Gemini.
    follow_up_text = follow_up_service.generate_follow_up_question(
        original_question=question.body,
        transcript_text=transcript.text,
        job_role=session.job_role,
        job_description=session.job_description,
    )

    follow_up = FollowUpQuestion(
        session_id=session_id,
        original_question_id=body.question_id,
        parent_audio_response_id=body.response_id,
        body=follow_up_text,
        depth=1,
    )
    db.add(follow_up)
    db.commit()
    db.refresh(follow_up)

    return FollowUpQuestionResponse.model_validate(follow_up)


@router.get(
    "/{session_id}/conversation-history",
    response_model=list[ConversationTurnResponse],
)
def get_conversation_history(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ConversationTurnResponse]:
    """Return all original questions and their follow-ups for a session."""
    interview_service.get_session_or_404(db, session_id, current_user.id)

    questions = (
        db.query(Question)
        .filter(Question.session_id == session_id)
        .order_by(Question.sequence_order)
        .all()
    )

    result: list[ConversationTurnResponse] = []
    for q in questions:
        follow_ups = (
            db.query(FollowUpQuestion)
            .filter(FollowUpQuestion.original_question_id == q.id)
            .order_by(FollowUpQuestion.created_at)
            .all()
        )
        result.append(
            ConversationTurnResponse(
                question_id=q.id,
                question_body=q.body,
                sequence_order=q.sequence_order,
                follow_ups=[
                    FollowUpQuestionResponse.model_validate(fu) for fu in follow_ups
                ],
            )
        )

    return result
