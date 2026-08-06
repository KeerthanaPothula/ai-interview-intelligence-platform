"""Pydantic schemas for the recruiter dashboard endpoints."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class CandidateResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    name: str
    email: str
    role: str
    resume_score: int | None = Field(
        description="Heuristic ATS estimate from the candidate's latest resume, or null if none uploaded."
    )
    interview_score: int = Field(
        description="Latest completed interview's final score, 0-100."
    )
    communication: int = Field(
        description="Average communication score across the interview, 0-100."
    )
    technical: int = Field(
        description="Average technical score across the interview, 0-100."
    )
    sessions_completed: int
    status: str = Field(
        description="Recruiter pipeline status, persisted on the session: "
        "applied, reviewing, interviewed, shortlisted, rejected, or hired. "
        "Defaults to 'applied' until a recruiter changes it."
    )
    applied_days: int = Field(
        description="Days since the candidate's latest completed session."
    )


class CandidateSummary(BaseModel):
    total_candidates: int
    shortlisted_count: int
    avg_resume_score: float | None
    avg_interview_score: float | None


class CandidateListResponse(BaseModel):
    items: list[CandidateResponse]
    total: int
    summary: CandidateSummary


class UpdateCandidateStatusRequest(BaseModel):
    status: str = Field(
        description="One of: applied, reviewing, interviewed, shortlisted, rejected, hired."
    )
