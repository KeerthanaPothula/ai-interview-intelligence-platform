from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class InterviewReadinessResponse(BaseModel):
    """A transparent, weighted-average readiness summary for a session.

    Not a prediction of a real-world interview or hiring outcome — see
    app/services/prediction_service.py for the exact (non-ML) formula.
    """

    id: uuid.UUID
    session_id: uuid.UUID
    readiness_score: float | None
    percentile_rank: float | None
    readiness_level: str | None
    scoring_method: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class CoachingPlanResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    plan_7_day: list[str] | None = None
    plan_14_day: list[str] | None = None
    plan_30_day: list[str] | None = None
    focus_areas: list[str] | None = None
    model_used: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class BenchmarkResponse(BaseModel):
    user_average_score: float | None
    percentile_rank: float | None
    total_platform_responses: int
    user_responses_analyzed: int
