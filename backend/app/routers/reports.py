"""Session-level final report endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.models.analysis import AudioResponse, InterviewAnalysis, Transcript
from app.models.features import SessionReport, VoiceAnalysis
from app.models.interview import InterviewSession, Question
from app.models.user import User
from app.schemas.features import SessionReportResponse
from app.services import report_service

router = APIRouter(prefix="/api/v1/interviews", tags=["Reports"])


def _get_owned_session_or_404(
    db: Session, session_id: uuid.UUID, user_id: uuid.UUID
) -> InterviewSession:
    session = (
        db.query(InterviewSession)
        .filter(
            InterviewSession.id == session_id,
            InterviewSession.user_id == user_id,
        )
        .first()
    )
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


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
    session = _get_owned_session_or_404(db, session_id, current_user.id)

    # Collect all questions and transcripts for the session.
    questions = (
        db.query(Question)
        .filter(Question.session_id == session_id)
        .order_by(Question.sequence_order)
        .all()
    )

    questions_and_transcripts: list[dict] = []
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
    voice_analytics = [
        {"confidence_score": v.confidence_score}
        for v in voice_rows
    ]

    report_data = report_service.generate_session_report(
        job_role=session.job_role,
        job_description=session.job_description,
        questions_and_transcripts=questions_and_transcripts,
        analyses=analyses,
        voice_analytics=voice_analytics,
    )

    # Upsert: delete existing report if present, then insert fresh.
    existing = (
        db.query(SessionReport)
        .filter(SessionReport.session_id == session_id)
        .first()
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
    _get_owned_session_or_404(db, session_id, current_user.id)

    report = (
        db.query(SessionReport)
        .filter(SessionReport.session_id == session_id)
        .first()
    )
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No report found for this session. POST to /report/generate first.",
        )

    return SessionReportResponse.model_validate(report)
