"""Session-level final report endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import API_V1_PREFIX
from app.core.rate_limit import enforce_ai_rate_limit
from app.core.deps import get_current_user
from app.core.exceptions import ResourceNotFound, ValidationError
from app.database import get_db
from app.models.analysis import AudioResponse, InterviewAnalysis, Transcript
from app.models.conversation import ConversationTurn
from app.models.features import SessionReport, VoiceAnalysis
from app.models.interview import Question
from app.models.user import User
from app.schemas.features import SessionReportResponse
from app.services import (
    analytics_service,
    interview_service,
    recruiter_service,
    report_service,
)

router = APIRouter(prefix=f"{API_V1_PREFIX}/interviews", tags=["Reports"])


def _collect_live_interview_qa(db: Session, live_session_id: uuid.UUID) -> list[dict]:
    """Build questions_and_transcripts from a live interview's ConversationTurns.

    Live interviews have no AudioResponse/Transcript/InterviewAnalysis rows —
    each turn already carries the question and the candidate's answer as
    plain text. Turns with no answer yet (response_text is None — e.g. the
    interview's final question, which is asked but never followed up) are
    included with an empty transcript rather than dropped, matching the
    upload-flow behavior of passing through whatever transcript text exists.
    """
    turns = (
        db.query(ConversationTurn)
        .filter(ConversationTurn.live_session_id == live_session_id)
        .order_by(ConversationTurn.turn_number)
        .all()
    )
    return [
        {"question": t.question_text, "transcript": t.response_text or ""}
        for t in turns
    ]


@router.post(
    "/{session_id}/report/generate",
    response_model=SessionReportResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_ai_rate_limit)],
)
def generate_report(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SessionReportResponse:
    """Generate (or regenerate) a holistic session report using Gemini."""
    session = interview_service.get_session_or_404(db, session_id, current_user.id)

    if session.live_session_id is not None:
        # Live interview mirror: no AudioResponse/Transcript/InterviewAnalysis
        # rows exist — the Q&A comes directly from ConversationTurn text, and
        # scores are the genuine per-answer ConversationTurnAnalysis rows, read
        # through the same source the Dashboard uses (owner-only, completed
        # interviews only). Unanswered turns have no row and add nothing.
        # There is no audio, so voice_analytics (and the report's voice-based
        # confidence_score) stays empty rather than being invented.
        questions_and_transcripts = _collect_live_interview_qa(
            db, session.live_session_id
        )
        sa = analytics_service.scored_answers(current_user.id)
        live_rows = db.execute(
            select(sa.c.overall, sa.c.comm, sa.c.tech, sa.c.ps).where(
                sa.c.session_id == session.id
            )
        ).all()
        analyses: list[dict] = [
            {
                "overall_score": float(r.overall),
                "communication_score": float(r.comm),
                "technical_score": float(r.tech),
                "problem_solving_score": float(r.ps),
            }
            for r in live_rows
        ]
        voice_analytics: list[dict] = []
    else:
        # Collect all questions and transcripts for the session.
        questions = (
            db.query(Question)
            .filter(Question.session_id == session_id)
            .order_by(Question.sequence_order)
            .all()
        )

        # One answer per question: its latest completed recording. A
        # question can be re-recorded, and the transcript Gemini judges and
        # the scores/voice metrics below must all describe that same answer
        # — never a mix of attempts, and never whichever row comes first.
        responses = (
            db.query(AudioResponse)
            .filter(
                AudioResponse.question_id.in_([q.id for q in questions]),
                AudioResponse.status == "completed",
            )
            .order_by(
                AudioResponse.question_id,
                AudioResponse.created_at.desc(),
                AudioResponse.id.desc(),
            )
            .all()
        )
        latest_by_question: dict[uuid.UUID, AudioResponse] = {}
        for response in responses:
            latest_by_question.setdefault(response.question_id, response)

        reported_ids = [
            latest_by_question[q.id].id
            for q in questions
            if q.id in latest_by_question
        ]
        transcripts = (
            db.query(Transcript)
            .filter(Transcript.audio_response_id.in_(reported_ids))
            .all()
        )
        transcript_by_response = {t.audio_response_id: t.text for t in transcripts}
        questions_and_transcripts = [
            {
                "question": q.body,
                "transcript": transcript_by_response.get(latest_by_question[q.id].id, ""),
            }
            for q in questions
            if q.id in latest_by_question
        ]

        # Analyses of exactly the reported answers.
        analyses_rows = (
            db.query(InterviewAnalysis)
            .filter(InterviewAnalysis.audio_response_id.in_(reported_ids))
            .all()
        )
        analyses = [
            {
                "overall_score": float(a.overall_score),
                "communication_score": float(a.communication_score),
                "technical_score": float(a.technical_score),
                "problem_solving_score": float(a.problem_solving_score),
            }
            for a in analyses_rows
        ]

        # Voice analytics of exactly the reported answers.
        voice_rows = (
            db.query(VoiceAnalysis)
            .filter(VoiceAnalysis.audio_response_id.in_(reported_ids))
            .all()
        )
        voice_analytics = [{"confidence_score": v.confidence_score} for v in voice_rows]

    # Without a single real answer Gemini would judge strengths, weaknesses
    # and readiness from nothing. Unscored answers still count. Checked
    # before any existing report is replaced, so that one stays intact.
    if not any((qt["transcript"] or "").strip() for qt in questions_and_transcripts):
        raise ValidationError(
            "This interview needs at least one answered question before a "
            "report can be generated."
        )

    report_data = report_service.generate_session_report(
        job_role=session.job_role,
        job_description=session.job_description,
        questions_and_transcripts=questions_and_transcripts,
        analyses=analyses,
        voice_analytics=voice_analytics,
    )

    # Upsert: delete existing report if present, then insert fresh.
    existing = (
        db.query(SessionReport).filter(SessionReport.session_id == session_id).first()
    )
    if existing is not None:
        db.delete(existing)
        db.flush()

    report = SessionReport(session_id=session_id, **report_data)
    db.add(report)
    db.commit()
    db.refresh(report)

    return SessionReportResponse.model_validate(report)


@router.get("/{session_id}/report", response_model=SessionReportResponse)
def get_report(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SessionReportResponse:
    """Retrieve the existing session report (404 if not yet generated).

    Readable by the session's owner, or by a Recruiter/Admin/Super Admin
    for a candidate inside their organization scope — see
    recruiter_service.get_viewable_session_or_404.
    """
    recruiter_service.get_viewable_session_or_404(db, session_id, current_user)

    report = (
        db.query(SessionReport).filter(SessionReport.session_id == session_id).first()
    )
    if report is None:
        raise ResourceNotFound(
            "No report found for this session. POST to /report/generate first."
        )

    return SessionReportResponse.model_validate(report)
