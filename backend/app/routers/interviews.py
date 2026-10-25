from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.constants import API_V1_PREFIX
from app.core.rate_limit import enforce_ai_rate_limit
from app.core.deps import get_current_user
from app.core.pagination import PaginationParams, pagination_params
from app.core.permissions import can_create_interview, can_generate_questions
from app.database import get_db
from app.models.interview import (
    SESSION_STATUS_DRAFT,
    SESSION_STATUS_IN_PROGRESS,
    Question,
    TextAnswer,
)
from app.models.user import User
from app.schemas.interview import (
    QuestionResponse,
    SessionCreate,
    SessionDetailResponse,
    SessionListResponse,
    SessionUpdate,
    TextAnswerCreate,
    TextAnswerResponse,
)
from app.services import evaluation_service
from app.core.exceptions import AIServiceError
from app.services import interview_service, question_service, recruiter_service

router = APIRouter(
    prefix=f"{API_V1_PREFIX}/interviews",
    tags=["Interviews"],
)


# ---------------------------------------------------------------------------
# Session endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/",
    response_model=SessionDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new interview session",
)
def create_session(
    data: SessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(can_create_interview()),
) -> SessionDetailResponse:
    """Create an interview session owned by the authenticated user.

    The session is created in 'draft' status. Questions are generated in a
    separate call to POST /{session_id}/questions/generate.

    Authorization: Candidate (or Super Admin). Never Recruiter or Admin.
    """
    session = interview_service.create_session(db, current_user.id, data)
    return SessionDetailResponse.model_validate(session).model_copy(
        update={"response_count": 0}
    )


@router.get(
    "/",
    response_model=list[SessionListResponse],
    summary="List the authenticated user's interview sessions",
)
def list_sessions(
    pagination: PaginationParams = Depends(pagination_params),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[SessionListResponse]:
    """Return a paginated list of sessions belonging to the authenticated user.

    Ordered newest first (created_at DESC). Sessions belonging to other users
    are never returned — isolation is enforced in the service layer by
    filtering on user_id.

    Authentication: Bearer token required.
    """
    sessions = interview_service.list_sessions(
        db, current_user.id, skip=pagination.skip, limit=pagination.limit
    )
    return [SessionListResponse.model_validate(s) for s in sessions]


@router.get(
    "/{session_id}",
    response_model=SessionDetailResponse,
    summary="Get a single interview session with its questions",
)
def get_session(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SessionDetailResponse:
    """Return full session details, including ordered questions and response count.

    Authentication: Bearer token required.
    Ownership: returns HTTP 404 if the session does not exist or belongs to
    another user. HTTP 403 is never returned — ownership mismatch is
    indistinguishable from non-existence to the caller. Recruiter/Admin/
    Super Admin may also read a pipeline candidate's session inside their
    organization scope (it heads the "Open report" page) — see
    recruiter_service.get_viewable_session_or_404.
    """
    session = recruiter_service.get_viewable_session_or_404(
        db, session_id, current_user
    )
    response_count = len(session.audio_responses)
    return SessionDetailResponse.model_validate(session).model_copy(
        update={"response_count": response_count}
    )


@router.patch(
    "/{session_id}",
    response_model=SessionDetailResponse,
    summary="Partially update a draft interview session",
)
def update_session(
    session_id: uuid.UUID,
    data: SessionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SessionDetailResponse:
    """Apply a partial update to a session in 'draft' status.

    Only fields present in the request body are updated (PATCH semantics).
    Omitted fields are left unchanged.

    Authentication: Bearer token required.
    Ownership: HTTP 404 if not found or owned by another user.
    Status gate: HTTP 409 if session.status != 'draft'.
    """
    session = interview_service.get_session_or_404(db, session_id, current_user.id)
    session = interview_service.update_session(db, session, data)
    response_count = len(session.audio_responses)
    return SessionDetailResponse.model_validate(session).model_copy(
        update={"response_count": response_count}
    )


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an interview session",
)
def delete_session(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Delete a session and all its owned rows (questions, audio responses).

    Cascade chain (enforced by ORM + DB):
      session → questions (ORM cascade="all, delete-orphan")
      questions → audio_responses (DB ON DELETE CASCADE)
      session → audio_responses (DB ON DELETE CASCADE on session_id)

    Audio files on disk are NOT removed here. A cleanup task (Week 5+) is
    responsible for reconciling DB rows with filesystem state.

    Authentication: Bearer token required.
    Ownership: HTTP 404 if not found or owned by another user.
    Returns: 204 No Content on success.
    """
    session = interview_service.get_session_or_404(db, session_id, current_user.id)
    interview_service.delete_session(db, session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Question endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/{session_id}/questions/generate",
    response_model=list[QuestionResponse],
    summary="Generate interview questions via Gemini",
    dependencies=[Depends(enforce_ai_rate_limit)],
)
def generate_questions(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(can_generate_questions()),
) -> list[QuestionResponse]:
    """Generate interview questions for a draft session using Gemini.

    Calls Gemini with the session's job_role and job_description, validates
    the response, replaces any existing questions, and returns the ordered
    new question set.

    Why draft-only:
        Once recordings begin, questions are referenced by audio_response rows
        via question_id. Regenerating questions would delete those Question
        rows via ON DELETE CASCADE, destroying the user's recorded answers.

    Generation order guarantee:
        Gemini is called first. Existing questions are deleted only after a
        valid Gemini response is received. A Gemini failure leaves the
        previous questions intact.

    Authentication: Bearer token required.
    Ownership: HTTP 404 if not found or owned by another user.
    Status gate: HTTP 409 if session.status != 'draft'.
    Gemini errors: HTTP 502 (unavailable/invalid) or 429 (rate limited).
    """
    session = interview_service.get_session_or_404(db, session_id, current_user.id)

    # Router-level draft gate — fail fast before entering the service.
    # The service enforces the same rule internally; this guard ensures
    # the check fires even if the service implementation changes.
    if session.status != SESSION_STATUS_DRAFT:
        raise HTTPException(
            status_code=409,
            detail="Questions can only be generated for draft sessions.",
        )

    questions = question_service.generate_and_save(db, session)
    return [QuestionResponse.model_validate(q) for q in questions]


@router.get(
    "/{session_id}/questions",
    response_model=list[QuestionResponse],
    summary="List questions for an interview session",
)
def get_questions(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[QuestionResponse]:
    """Return all questions for a session, ordered by sequence_order ascending.

    Authentication: Bearer token required.
    Ownership: HTTP 404 if session not found or owned by another user.
    Returns an empty list if no questions have been generated yet.
    """
    # Ownership check — confirms the session exists and belongs to this user
    # before returning any question data.
    interview_service.get_session_or_404(db, session_id, current_user.id)
    questions = question_service.get_questions(db, session_id)
    return [QuestionResponse.model_validate(q) for q in questions]


def _answer_response(answer: TextAnswer) -> TextAnswerResponse:
    import json

    return TextAnswerResponse(
        id=answer.id,
        session_id=answer.session_id,
        question_id=answer.question_id,
        answer_text=answer.answer_text,
        overall_score=answer.overall_score,
        strengths=json.loads(answer.strengths) if answer.strengths else None,
        weaknesses=json.loads(answer.weaknesses) if answer.weaknesses else None,
        detailed_feedback=answer.detailed_feedback,
        created_at=answer.created_at,
    )


@router.get("/{session_id}/answers", response_model=list[TextAnswerResponse])
def list_text_answers(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[TextAnswerResponse]:
    interview_service.get_session_or_404(db, session_id, current_user.id)
    answers = db.scalars(
        select(TextAnswer).where(
            TextAnswer.session_id == session_id,
            TextAnswer.user_id == current_user.id,
        )
    ).all()
    return [_answer_response(answer) for answer in answers]


@router.post(
    "/{session_id}/questions/{question_id}/answers",
    response_model=TextAnswerResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_text_answer(
    session_id: uuid.UUID,
    question_id: uuid.UUID,
    data: TextAnswerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TextAnswerResponse:
    session = interview_service.get_session_or_404(db, session_id, current_user.id)
    question = db.scalar(
        select(Question).where(
            Question.id == question_id, Question.session_id == session.id
        )
    )
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found.")
    answer_text = data.answer_text.strip()
    if not answer_text:
        raise HTTPException(status_code=422, detail="Answer cannot be blank.")
    if db.scalar(select(TextAnswer.id).where(TextAnswer.question_id == question_id)):
        raise HTTPException(status_code=409, detail="An answer was already submitted for this question.")

    answer = TextAnswer(
        session_id=session.id,
        question_id=question.id,
        user_id=current_user.id,
        answer_text=answer_text,
    )
    # Freeze the generated question set once a candidate has started answering;
    # the existing draft-only regeneration flow would otherwise cascade-delete it.
    session.status = SESSION_STATUS_IN_PROGRESS
    # The existing evaluator accepts answer text directly. Evaluation is
    # optional: evaluator outages never discard a candidate's answer.
    try:
        evaluation = evaluation_service.generate_evaluation(
            transcript_text=answer_text,
            question=question.body,
            job_role=session.job_role,
            job_description=session.job_description,
        )
        answer.overall_score = evaluation["overall_score"]
        answer.strengths = evaluation["strengths"]
        answer.weaknesses = evaluation["weaknesses"]
        answer.detailed_feedback = evaluation["detailed_feedback"]
    except AIServiceError:
        pass

    db.add(answer)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="An answer was already submitted for this question.")
    db.refresh(answer)
    return _answer_response(answer)
