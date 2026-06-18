"""Interview prediction, career coaching, and benchmarking endpoints."""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.analysis import AudioResponse, InterviewAnalysis
from app.models.features import VoiceAnalysis, SessionReport
from app.models.interview import InterviewSession
from app.models.prediction import CoachingPlan, InterviewPrediction
from app.routers.auth import get_current_user
from app.schemas.prediction import (
    BenchmarkResponse,
    CoachingPlanResponse,
    InterviewPredictionResponse,
)
from app.services import benchmark_service, career_coach_service, prediction_service
from app.models.user import User

router = APIRouter(tags=["Prediction & Coaching"])


def _get_session_or_404(
    session_id: uuid.UUID, user_id: uuid.UUID, db: Session
) -> InterviewSession:
    session = db.execute(
        select(InterviewSession).where(
            InterviewSession.id == session_id,
            InterviewSession.user_id == user_id,
        )
    ).scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Interview session not found")
    return session


def _get_session_averages(session_id: uuid.UUID, db: Session) -> dict:
    """Aggregate score averages and voice metrics for a session."""
    analyses = db.execute(
        select(InterviewAnalysis)
        .join(AudioResponse, InterviewAnalysis.audio_response_id == AudioResponse.id)
        .where(AudioResponse.session_id == session_id)
    ).scalars().all()

    if not analyses:
        return {}

    def _avg(vals):
        clean = [float(v) for v in vals if v is not None]
        return sum(clean) / len(clean) if clean else 5.0

    voices = db.execute(
        select(VoiceAnalysis)
        .join(AudioResponse, VoiceAnalysis.audio_response_id == AudioResponse.id)
        .where(AudioResponse.session_id == session_id)
    ).scalars().all()

    return {
        "overall_score": _avg([a.overall_score for a in analyses]),
        "communication_score": _avg([a.communication_score for a in analyses]),
        "technical_score": _avg([a.technical_score for a in analyses]),
        "problem_solving_score": _avg([a.problem_solving_score for a in analyses]),
        "avg_confidence": _avg([v.confidence_score for v in voices]),
        "avg_speaking_rate": _avg([v.speaking_rate for v in voices]),
        "avg_filler_words": _avg([v.filler_word_count for v in voices]),
    }


@router.post(
    "/api/v1/interviews/{session_id}/predict",
    response_model=InterviewPredictionResponse,
    status_code=201,
)
def generate_prediction(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate a success probability prediction for this session."""
    session = _get_session_or_404(session_id, current_user.id, db)
    metrics = _get_session_averages(session_id, db)

    if not metrics:
        raise HTTPException(
            status_code=422,
            detail="No analyses found for this session. Process some responses first.",
        )

    prob, outcome = prediction_service.predict_success(**metrics)

    # Compute percentile vs all platform users
    all_scores_stmt = (
        select(InterviewAnalysis.overall_score)
        .join(AudioResponse, InterviewAnalysis.audio_response_id == AudioResponse.id)
    )
    all_scores = [float(s) for s in db.execute(all_scores_stmt).scalars().all() if s]
    percentile = prediction_service.compute_percentile(metrics["overall_score"], all_scores)

    # Upsert
    existing = db.execute(
        select(InterviewPrediction).where(InterviewPrediction.session_id == session_id)
    ).scalar_one_or_none()
    if existing:
        db.delete(existing)
        db.flush()

    pred = InterviewPrediction(
        session_id=session_id,
        success_probability=round(prob, 4),
        percentile_rank=percentile,
        predicted_outcome=outcome,
        feature_vector=json.dumps(metrics),
        model_version=prediction_service._MODEL_VERSION,
    )
    db.add(pred)
    db.commit()
    db.refresh(pred)
    return pred


@router.get(
    "/api/v1/interviews/{session_id}/prediction",
    response_model=InterviewPredictionResponse,
)
def get_prediction(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_session_or_404(session_id, current_user.id, db)
    pred = db.execute(
        select(InterviewPrediction).where(InterviewPrediction.session_id == session_id)
    ).scalar_one_or_none()
    if pred is None:
        raise HTTPException(status_code=404, detail="No prediction generated yet")
    return pred


@router.post(
    "/api/v1/interviews/{session_id}/coaching-plan",
    response_model=CoachingPlanResponse,
    status_code=201,
)
def generate_coaching_plan(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate a personalised 7/14/30-day coaching plan via Gemini."""
    session = _get_session_or_404(session_id, current_user.id, db)
    metrics = _get_session_averages(session_id, db)

    if not metrics:
        raise HTTPException(
            status_code=422,
            detail="No analyses found for this session.",
        )

    # Load weaknesses from session report if available
    weaknesses: list[str] = []
    report = db.execute(
        select(SessionReport).where(SessionReport.session_id == session_id)
    ).scalar_one_or_none()
    if report and report.weaknesses:
        try:
            weaknesses = json.loads(report.weaknesses)
        except Exception:
            pass

    readiness = report.readiness_level if report else None

    plan_data = career_coach_service.generate_coaching_plan(
        job_role=session.job_role,
        job_description=session.job_description,
        overall_score=metrics["overall_score"],
        communication_score=metrics["communication_score"],
        technical_score=metrics["technical_score"],
        problem_solving_score=metrics["problem_solving_score"],
        readiness_level=readiness,
        weaknesses=weaknesses,
    )

    # Upsert
    existing = db.execute(
        select(CoachingPlan).where(CoachingPlan.session_id == session_id)
    ).scalar_one_or_none()
    if existing:
        db.delete(existing)
        db.flush()

    plan = CoachingPlan(
        session_id=session_id,
        plan_7_day=json.dumps(plan_data.get("plan_7_day", [])),
        plan_14_day=json.dumps(plan_data.get("plan_14_day", [])),
        plan_30_day=json.dumps(plan_data.get("plan_30_day", [])),
        focus_areas=json.dumps(plan_data.get("focus_areas", [])),
        model_used=plan_data.get("model_used"),
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)

    return _coaching_response(plan)


@router.get(
    "/api/v1/interviews/{session_id}/coaching-plan",
    response_model=CoachingPlanResponse,
)
def get_coaching_plan(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_session_or_404(session_id, current_user.id, db)
    plan = db.execute(
        select(CoachingPlan).where(CoachingPlan.session_id == session_id)
    ).scalar_one_or_none()
    if plan is None:
        raise HTTPException(status_code=404, detail="No coaching plan generated yet")
    return _coaching_response(plan)


@router.get("/api/v1/analytics/benchmarks", response_model=BenchmarkResponse)
def get_benchmarks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the current user's performance percentile vs all platform users."""
    result = benchmark_service.get_user_benchmark(current_user.id, db)
    return BenchmarkResponse(**result)


def _coaching_response(plan: CoachingPlan) -> CoachingPlanResponse:
    """Deserialise JSON fields before building the response model."""

    def _parse(val: str | None) -> list[str] | None:
        if not val:
            return None
        try:
            return json.loads(val)
        except Exception:
            return None

    return CoachingPlanResponse(
        id=plan.id,
        session_id=plan.session_id,
        plan_7_day=_parse(plan.plan_7_day),
        plan_14_day=_parse(plan.plan_14_day),
        plan_30_day=_parse(plan.plan_30_day),
        focus_areas=_parse(plan.focus_areas),
        model_used=plan.model_used,
        created_at=plan.created_at,
    )
