"""Pydantic schemas for Phase 16 feature endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Voice Analytics
# ---------------------------------------------------------------------------


class VoiceAnalysisResponse(BaseModel):
    id: uuid.UUID
    audio_response_id: uuid.UUID
    speaking_rate: float | None
    average_pause_duration: float | None
    total_pause_time: float | None
    long_pause_count: int | None
    filler_word_count: int | None
    energy_consistency: float | None
    confidence_score: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Follow-Up Questions
# ---------------------------------------------------------------------------


class FollowUpRequest(BaseModel):
    question_id: uuid.UUID
    response_id: uuid.UUID


class FollowUpQuestionResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    original_question_id: uuid.UUID
    parent_audio_response_id: uuid.UUID | None
    body: str
    depth: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationTurnResponse(BaseModel):
    question_id: uuid.UUID
    question_body: str
    sequence_order: int
    follow_ups: list[FollowUpQuestionResponse]


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


class AnalyticsOverviewResponse(BaseModel):
    total_sessions: int
    completed_sessions: int
    average_overall_score: float | None
    total_responses_analyzed: int
    strongest_skill: str | None
    weakest_skill: str | None
    improvement_score: float | None


class SessionTrendResponse(BaseModel):
    session_id: uuid.UUID
    session_title: str
    created_at: datetime
    average_overall_score: float | None
    average_communication_score: float | None
    average_technical_score: float | None
    average_problem_solving_score: float | None
    average_confidence_score: float | None


# ---------------------------------------------------------------------------
# Session Report
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Activity Timeline
# ---------------------------------------------------------------------------


class ActivityEvent(BaseModel):
    event_type: str
    title: str
    subtitle: str | None
    created_at: datetime


class ActivityTimelineResponse(BaseModel):
    events: list[ActivityEvent]


# ---------------------------------------------------------------------------
# AI Insights
# ---------------------------------------------------------------------------


class InsightItem(BaseModel):
    text: str
    kind: str  # 'positive' | 'warning' | 'info'


class InsightsResponse(BaseModel):
    insights: list[InsightItem]


class SessionReportResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    overall_performance: str | None
    final_score: float | None
    confidence_score: int | None
    communication_score: float | None
    technical_score: float | None
    problem_solving_score: float | None
    strengths: str | None
    weaknesses: str | None
    improvement_plan: str | None
    readiness_level: str | None
    model_used: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
