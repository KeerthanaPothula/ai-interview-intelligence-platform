"""Recruiter dashboard endpoints.

See app/services/recruiter_service.py for why this has no role gate.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.constants import API_V1_PREFIX
from app.core.deps import get_current_user
from app.core.pagination import PaginationParams, pagination_params
from app.database import get_db
from app.models.user import User
from app.schemas.recruiter import CandidateListResponse, CandidateResponse, CandidateSummary
from app.services import recruiter_service

router = APIRouter(prefix=f"{API_V1_PREFIX}/recruiter", tags=["Recruiter"])


@router.get(
    "/candidates",
    response_model=CandidateListResponse,
    summary="List candidates aggregated from every user's latest completed interview",
)
def list_candidates(
    search: str | None = Query(default=None, max_length=200),
    status: str | None = Query(
        default=None, description="Filter by shortlisted, reviewing, pending, or rejected."
    ),
    sort_by: str = Query(default="interviewScore"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    pagination: PaginationParams = Depends(pagination_params),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CandidateListResponse:
    """
    Every registered user with at least one completed interview appears as
    a candidate row, scored from their latest completed session.

    Authentication: Bearer token required (any authenticated user).
    """
    items, total, summary = recruiter_service.list_candidates(
        db,
        search=search,
        status=status,
        sort_by=sort_by,
        sort_dir=sort_dir,
        skip=pagination.skip,
        limit=pagination.limit,
    )
    return CandidateListResponse(
        items=[
            CandidateResponse(
                id=c.id,
                session_id=c.session_id,
                name=c.name,
                email=c.email,
                role=c.role,
                resume_score=c.resume_score,
                interview_score=c.interview_score,
                communication=c.communication,
                technical=c.technical,
                sessions_completed=c.sessions_completed,
                status=c.status,
                applied_days=c.applied_days,
            )
            for c in items
        ],
        total=total,
        summary=CandidateSummary(**summary),
    )
