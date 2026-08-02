"""Admin dashboard endpoints.

See app/services/admin_service.py for why this has no role gate.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.constants import API_V1_PREFIX
from app.core.deps import get_current_user
from app.core.pagination import PaginationParams, pagination_params
from app.database import get_db
from app.models.user import User
from app.schemas.admin import (
    AdminActivityEvent,
    AdminOverviewResponse,
    AdminUserListResponse,
    JobRoleCount,
)
from app.services import admin_service

router = APIRouter(prefix=f"{API_V1_PREFIX}/admin", tags=["Admin"])


@router.get(
    "/overview",
    response_model=AdminOverviewResponse,
    summary="Platform-wide usage, AI activity, and storage statistics",
)
def get_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AdminOverviewResponse:
    return admin_service.get_overview(db)


@router.get(
    "/users",
    response_model=AdminUserListResponse,
    summary="List every registered user with their session activity",
)
def list_users(
    search: str | None = Query(default=None, max_length=200),
    pagination: PaginationParams = Depends(pagination_params),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AdminUserListResponse:
    items, total = admin_service.list_users(
        db, search=search, skip=pagination.skip, limit=pagination.limit
    )
    return AdminUserListResponse(items=items, total=total)


@router.get(
    "/jobs",
    response_model=list[JobRoleCount],
    summary="Distinct job roles interviewed for, ranked by session count",
)
def list_job_roles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[JobRoleCount]:
    return admin_service.list_job_roles(db)


@router.get(
    "/activity",
    response_model=list[AdminActivityEvent],
    summary="Recent platform-wide activity across every user",
)
def list_activity(
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AdminActivityEvent]:
    return admin_service.list_activity(db, limit=limit)
