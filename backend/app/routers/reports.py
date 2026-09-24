"""Session-level final report endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import API_V1_PREFIX
from app.core.deps import get_current_user
from app.core.exceptions import ResourceNotFound
from app.database import get_db
from app.models.analysis import AudioResponse, InterviewAnalysis, Transcript
from app.models.conversation import ConversationTurn
from app.models.features import SessionReport, VoiceAnalysis
from app.models.interview import Question
from app.models.user import User
from app.schemas.features import SessionReportResponse
from app.services import analytics_service, interview_service, report_service

router = APIRouter(prefix=f"{API_V1_PREFIX}/interviews", tags=["Reports"])


def _collect_live_interview_qa(
    db: Session, live_session_id: uuid.UUID
) -> list[dict]:
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

        questions_and_transcripts = []
        for q in questions:
            resp = (
                db.query(AudioResponse)
                .filter(
                    AudioResponse.question_id == q.id,
                    AudioResponse.status == "completed",
                )
                .first()
            )
            if resp is None:
                continue
            transcript = (
                db.query(Transcript)
                .filter(Transcript.audio_response_id == resp.id)
                .first()
            )
            questions_and_transcripts.append(
                {
                    "question": q.body,
                    "transcript": transcript.text if transcript else "",
                }
            )

        # Collect all analyses for this session.
        analyses_rows = (
            db.query(InterviewAnalysis)
            .join(AudioResponse, InterviewAnalysis.audio_response_id == AudioResponse.id)
            .filter(AudioResponse.session_id == session_id)
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

        # Collect voice analytics.
        voice_rows = (
            db.query(VoiceAnalysis)
            .join(AudioResponse, VoiceAnalysis.audio_response_id == AudioResponse.id)
            .filter(AudioResponse.session_id == session_id)
            .all()
        )
        voice_analytics = [{"confidence_score": v.confidence_score} for v in voice_rows]

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
    """Retrieve the existing session report (404 if not yet generated)."""
    interview_service.get_session_or_404(db, session_id, current_user.id)

    report = (
        db.query(SessionReport).filter(SessionReport.session_id == session_id).first()
    )
    if report is None:
        raise ResourceNotFound(
            "No report found for this session. POST to /report/generate first."
        )

    return SessionReportResponse.model_validate(report)
