"""Pydantic schemas for the admin dashboard endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class AdminUserResponse(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str
    created_at: datetime
    sessions_completed: int
    latest_session_at: datetime | None


class AdminUserListResponse(BaseModel):
    items: list[AdminUserResponse]
    total: int


class AiUsageStats(BaseModel):
    questions_generated: int
    transcriptions_completed: int
    evaluations_completed: int
    reports_generated: int
    coaching_plans_generated: int
    predictions_generated: int


class StorageStats(BaseModel):
    audio_bytes: int
    audio_file_count: int
    resume_bytes: int
    resume_file_count: int


class DailyCount(BaseModel):
    date: str
    count: int


class AdminOverviewResponse(BaseModel):
    total_users: int
    total_sessions: int
    sessions_by_status: dict[str, int]
    total_reports: int
    avg_platform_score: float | None
    total_resumes: int
    ai_usage: AiUsageStats
    storage: StorageStats
    signups_last_30_days: list[DailyCount]
    sessions_last_30_days: list[DailyCount]


class JobRoleCount(BaseModel):
    role: str
    session_count: int


class AdminActivityEvent(BaseModel):
    event_type: str
    title: str
    subtitle: str | None
    created_at: datetime
