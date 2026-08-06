"""Recruiter dashboard endpoints.

Role-gated via app.core.permissions.can_view_candidates /
can_shortlist (Recruiter, Admin, Super Admin — never Candidate).
Organization-scoped in the service layer: see
app.services.recruiter_service.scope_organization_id.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.constants import API_V1_PREFIX
from app.core.pagination import PaginationParams, pagination_params
from app.core.permissions import can_shortlist, can_view_candidates
from app.database import get_db
from app.models.user import User
from app.schemas.recruiter import (
    CandidateListResponse,
    CandidateResponse,
    CandidateSummary,
    UpdateCandidateStatusRequest,
)
from app.services import recruiter_service

router = APIRouter(prefix=f"{API_V1_PREFIX}/recruiter", tags=["Recruiter"])


def _to_response(c: recruiter_service.Candidate) -> CandidateResponse:
    return CandidateResponse(
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


@router.get(
    "/candidates",
    response_model=CandidateListResponse,
    summary="List candidates aggregated from every user's latest completed interview",
)
def list_candidates(
    search: str | None = Query(default=None, max_length=200),
    status: str | None = Query(
        default=None,
        description="Filter by applied, reviewing, interviewed, shortlisted, rejected, or hired.",
    ),
    sort_by: str = Query(default="interviewScore"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    pagination: PaginationParams = Depends(pagination_params),
    db: Session = Depends(get_db),
    current_user: User = Depends(can_view_candidates()),
) -> CandidateListResponse:
    """
    Every organization member with at least one completed, reported
    interview appears as a candidate row, scored from their latest
    completed session.

    Authorization: Recruiter, Admin, or Super Admin. A Recruiter sees only
    their own organization's candidates; Admin/Super Admin see every
    organization's.
    """
    items, total, summary = recruiter_service.list_candidates(
        db,
        current_user=current_user,
        search=search,
        status=status,
        sort_by=sort_by,
        sort_dir=sort_dir,
        skip=pagination.skip,
        limit=pagination.limit,
    )
    return CandidateListResponse(
        items=[_to_response(c) for c in items],
        total=total,
        summary=CandidateSummary(**summary),
    )


@router.patch(
    "/candidates/{session_id}/status",
    response_model=CandidateResponse,
    summary="Change a candidate's recruiter-pipeline status",
)
def update_candidate_status(
    session_id: uuid.UUID,
    body: UpdateCandidateStatusRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(can_shortlist()),
) -> CandidateResponse:
    """
    Move a candidate through the recruiter pipeline: applied -> reviewing
    -> interviewed -> shortlisted / rejected / hired. Persisted on the
    underlying InterviewSession (recruiter_status), not derived.

    Authorization: Recruiter, Admin, or Super Admin. A Recruiter can only
    change the status of candidates in their own organization (404, not
    403, for a candidate outside it — see recruiter_service for why).
    """
    candidate = recruiter_service.update_candidate_status(
        db,
        session_id=session_id,
        new_status=body.status,
        current_user=current_user,
    )
    return _to_response(candidate)
