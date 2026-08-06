"""Pydantic schemas for the admin dashboard endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class AdminUserResponse(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str
    role: str
    organization_id: uuid.UUID | None
    organization_name: str | None
    is_active: bool
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


# ---------------------------------------------------------------------------
# Organization management (Phase 9 — Admin/Super Admin only)
# ---------------------------------------------------------------------------


class OrganizationResponse(BaseModel):
    id: uuid.UUID
    name: str
    is_active: bool
    created_at: datetime
    recruiter_count: int
    candidate_count: int


class OrganizationListResponse(BaseModel):
    items: list[OrganizationResponse]
    total: int


class CreateOrganizationRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class CreateRecruiterRequest(BaseModel):
    """Admin-only recruiter provisioning. Deliberately separate from
    UserCreate (self-registration) — a recruiter account can only ever be
    created by an Admin/Super Admin, never by the frontend register form,
    and always already assigned to an organization."""

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(..., min_length=1, max_length=255)
    organization_id: uuid.UUID


class UpdateUserRoleRequest(BaseModel):
    role: str = Field(description="One of: super_admin, admin, recruiter, candidate.")
