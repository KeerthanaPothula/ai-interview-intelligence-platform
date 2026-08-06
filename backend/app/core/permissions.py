"""Named permission dependencies for FastAPI routes.

Every function here returns a FastAPI dependency (built from
app.core.deps.require_role / require_any_role) rather than performing a
check itself — there is exactly one place authorization logic lives
(require_role/require_any_role), and exactly one place the DB-sourced
`current_user.role` is read (get_current_user). This module only names
*what* each permission means in product terms, so routers read as
intent ("can_view_candidates()") rather than as role trivia
("RECRUITER or ADMIN or SUPER_ADMIN").

Usage:
    @router.post("/interviews")
    def create_session(
        current_user: User = Depends(can_create_interview()),
    ):
        ...

Add a new permission by adding a new function here, not by inlining a
fresh require_role(...)/require_any_role(...) call at a route — keeps
"who can do X" answerable by reading this one file.
"""

from __future__ import annotations

from typing import Callable

from app.core.deps import require_any_role, require_role
from app.models.role import Role
from app.models.user import User

# ---------------------------------------------------------------------------
# Candidate
# ---------------------------------------------------------------------------


def can_create_interview() -> Callable[..., User]:
    """Create/take practice interview sessions.

    CANDIDATE, plus SUPER_ADMIN ("Super Admin: Everything" — the one role
    with no page it's excluded from). Deliberately excludes plain ADMIN:
    "Admin cannot take interviews" is an explicit product requirement —
    Admin manages the platform, it doesn't use the candidate workflow.
    RECRUITER is excluded for the same reason ("Recruiter cannot create
    interviews").
    """
    return require_any_role(Role.CANDIDATE, Role.SUPER_ADMIN)


def can_upload_resume() -> Callable[..., User]:
    return require_any_role(Role.CANDIDATE, Role.SUPER_ADMIN)


def can_generate_questions() -> Callable[..., User]:
    return require_any_role(Role.CANDIDATE, Role.SUPER_ADMIN)


# ---------------------------------------------------------------------------
# Recruiter
# ---------------------------------------------------------------------------


def can_view_candidates() -> Callable[..., User]:
    """View the candidate pipeline. Admin/Super Admin can view every
    organization's candidates (see recruiter_service's org-scoping —
    unscoped for these two roles); a Recruiter sees only their own
    organization's."""
    return require_any_role(Role.RECRUITER, Role.ADMIN, Role.SUPER_ADMIN)


def can_shortlist() -> Callable[..., User]:
    """Change a candidate's recruiter-pipeline status (applied -> ... ->
    hired/rejected)."""
    return require_any_role(Role.RECRUITER, Role.ADMIN, Role.SUPER_ADMIN)


def can_download_reports() -> Callable[..., User]:
    return require_any_role(Role.RECRUITER, Role.ADMIN, Role.SUPER_ADMIN)


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------


def can_manage_users() -> Callable[..., User]:
    """Create/deactivate recruiter accounts, assign a recruiter to an
    organization. Does NOT include changing a user's *role* — see
    can_assign_roles, which is Super-Admin-only per Phase 2."""
    return require_any_role(Role.ADMIN, Role.SUPER_ADMIN)


def can_view_platform() -> Callable[..., User]:
    """Platform-wide analytics/usage/storage stats (the existing
    /api/v1/admin/overview family)."""
    return require_any_role(Role.ADMIN, Role.SUPER_ADMIN)


def can_manage_organizations() -> Callable[..., User]:
    """Create/deactivate organizations."""
    return require_any_role(Role.ADMIN, Role.SUPER_ADMIN)


# ---------------------------------------------------------------------------
# Super Admin
# ---------------------------------------------------------------------------


def can_assign_roles() -> Callable[..., User]:
    """Change any user's role. Deliberately Super-Admin-only, not
    Admin-inclusive: an Admin who could promote arbitrary users to Admin
    (or to Super Admin) would be a privilege-escalation path, which is
    exactly what Phase 2/13 call out to prevent."""
    return require_role(Role.SUPER_ADMIN)
