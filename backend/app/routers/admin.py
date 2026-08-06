"""Admin dashboard endpoints.

Role-gated via app.core.permissions: can_view_platform (read-only stats),
can_manage_users (recruiter provisioning, activate/deactivate),
can_manage_organizations (create/deactivate orgs), can_assign_roles
(Super Admin only — role changes). See that module's docstrings for the
exact role sets.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.constants import API_V1_PREFIX
from app.core.permissions import (
    can_assign_roles,
    can_manage_organizations,
    can_manage_users,
    can_view_platform,
)
from app.database import get_db
from app.models.user import User
from app.schemas.admin import (
    AdminActivityEvent,
    AdminOverviewResponse,
    AdminUserListResponse,
    AdminUserResponse,
    CreateOrganizationRequest,
    CreateRecruiterRequest,
    JobRoleCount,
    OrganizationListResponse,
    OrganizationResponse,
    UpdateUserRoleRequest,
)
from app.schemas.auth import DetailResponse
from app.services import admin_service

router = APIRouter(prefix=f"{API_V1_PREFIX}/admin", tags=["Admin"])


# ---------------------------------------------------------------------------
# Platform stats (read-only) — Admin, Super Admin
# ---------------------------------------------------------------------------


@router.get(
    "/overview",
    response_model=AdminOverviewResponse,
    summary="Platform-wide usage, AI activity, and storage statistics",
)
def get_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(can_view_platform()),
) -> AdminOverviewResponse:
    return admin_service.get_overview(db)


@router.get(
    "/users",
    response_model=AdminUserListResponse,
    summary="List every registered user with their session activity",
)
def list_users(
    search: str | None = Query(default=None, max_length=200),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(can_view_platform()),
) -> AdminUserListResponse:
    items, total = admin_service.list_users(db, search=search, skip=skip, limit=limit)
    return AdminUserListResponse(items=items, total=total)


@router.get(
    "/jobs",
    response_model=list[JobRoleCount],
    summary="Distinct job roles interviewed for, ranked by session count",
)
def list_job_roles(
    db: Session = Depends(get_db),
    current_user: User = Depends(can_view_platform()),
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
    current_user: User = Depends(can_view_platform()),
) -> list[AdminActivityEvent]:
    return admin_service.list_activity(db, limit=limit)


# ---------------------------------------------------------------------------
# Organization management — Admin, Super Admin
# ---------------------------------------------------------------------------


@router.get(
    "/organizations",
    response_model=OrganizationListResponse,
    summary="List every organization with recruiter/candidate counts",
)
def list_organizations(
    db: Session = Depends(get_db),
    current_user: User = Depends(can_view_platform()),
) -> OrganizationListResponse:
    items, total = admin_service.list_organizations(db)
    return OrganizationListResponse(items=items, total=total)


@router.post(
    "/organizations",
    response_model=OrganizationResponse,
    status_code=201,
    summary="Create a new organization",
)
def create_organization(
    body: CreateOrganizationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(can_manage_organizations()),
) -> OrganizationResponse:
    org = admin_service.create_organization(db, name=body.name)
    return OrganizationResponse(
        id=org.id,
        name=org.name,
        is_active=org.is_active,
        created_at=org.created_at,
        recruiter_count=0,
        candidate_count=0,
    )


@router.patch(
    "/organizations/{org_id}/deactivate",
    response_model=OrganizationResponse,
    summary="Deactivate an organization",
)
def deactivate_organization(
    org_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(can_manage_organizations()),
) -> OrganizationResponse:
    org = admin_service.set_organization_active(db, org_id=org_id, is_active=False)
    items, _ = admin_service.list_organizations(db)
    match = next((o for o in items if o.id == org.id), None)
    return match or OrganizationResponse(
        id=org.id,
        name=org.name,
        is_active=org.is_active,
        created_at=org.created_at,
        recruiter_count=0,
        candidate_count=0,
    )


@router.patch(
    "/organizations/{org_id}/activate",
    response_model=OrganizationResponse,
    summary="Reactivate a previously deactivated organization",
)
def activate_organization(
    org_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(can_manage_organizations()),
) -> OrganizationResponse:
    org = admin_service.set_organization_active(db, org_id=org_id, is_active=True)
    items, _ = admin_service.list_organizations(db)
    match = next((o for o in items if o.id == org.id), None)
    return match or OrganizationResponse(
        id=org.id,
        name=org.name,
        is_active=org.is_active,
        created_at=org.created_at,
        recruiter_count=0,
        candidate_count=0,
    )


# ---------------------------------------------------------------------------
# Recruiter provisioning — Admin, Super Admin
# ---------------------------------------------------------------------------


@router.post(
    "/recruiters",
    response_model=AdminUserResponse,
    status_code=201,
    summary="Create a recruiter account assigned to an organization",
)
def create_recruiter(
    body: CreateRecruiterRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(can_manage_users()),
) -> AdminUserResponse:
    recruiter = admin_service.create_recruiter(db, body)
    org_name = recruiter.organization.name if recruiter.organization else None
    return AdminUserResponse(
        id=recruiter.id,
        full_name=recruiter.full_name,
        email=recruiter.email,
        role=recruiter.role,
        organization_id=recruiter.organization_id,
        organization_name=org_name,
        is_active=recruiter.is_active,
        created_at=recruiter.created_at,
        sessions_completed=0,
        latest_session_at=None,
    )


# ---------------------------------------------------------------------------
# User activation — Admin, Super Admin
# ---------------------------------------------------------------------------


@router.patch(
    "/users/{user_id}/deactivate",
    response_model=DetailResponse,
    summary="Deactivate a user account (e.g. offboard a recruiter)",
)
def deactivate_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(can_manage_users()),
) -> DetailResponse:
    admin_service.set_user_active(
        db, user_id=user_id, is_active=False, acting_user=current_user
    )
    return DetailResponse(detail="Account deactivated.")


@router.patch(
    "/users/{user_id}/activate",
    response_model=DetailResponse,
    summary="Reactivate a previously deactivated user account",
)
def activate_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(can_manage_users()),
) -> DetailResponse:
    admin_service.set_user_active(
        db, user_id=user_id, is_active=True, acting_user=current_user
    )
    return DetailResponse(detail="Account reactivated.")


# ---------------------------------------------------------------------------
# Role assignment — Super Admin only
# ---------------------------------------------------------------------------


@router.patch(
    "/users/{user_id}/role",
    response_model=DetailResponse,
    summary="Change a user's role (Super Admin only)",
)
def update_user_role(
    user_id: uuid.UUID,
    body: UpdateUserRoleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(can_assign_roles()),
) -> DetailResponse:
    admin_service.set_user_role(
        db, user_id=user_id, new_role=body.role, acting_user=current_user
    )
    return DetailResponse(detail="Role updated. The affected user must log in again.")
