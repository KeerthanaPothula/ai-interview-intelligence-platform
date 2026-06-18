from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class InterviewPredictionResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    success_probability: float | None
    percentile_rank: float | None
    predicted_outcome: str | None
    model_version: str | None
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
