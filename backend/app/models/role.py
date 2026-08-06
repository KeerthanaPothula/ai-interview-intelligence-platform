from __future__ import annotations

import enum


class Role(str, enum.Enum):
    """Application roles. Stored as `.value` (a plain string) on User.role —
    same "VARCHAR + Python constants" convention as InterviewSession.status,
    not a normalized lookup table or a native DB ENUM (see the CHECK
    constraint on users.role in the migration for the DB-level guarantee).

    Not a linear hierarchy — do not compare roles by ordering. SUPER_ADMIN
    happens to be a superset of every other role's access, but ADMIN,
    RECRUITER, and CANDIDATE are peers scoped to disjoint workflows, not
    ascending privilege levels. Always express "any of these roles" via
    require_any_role(...) (app.core.deps), never via >=/<= comparisons.
    """

    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    RECRUITER = "recruiter"
    CANDIDATE = "candidate"


ROLE_VALUES: frozenset[str] = frozenset(r.value for r in Role)

# New registrations always get this role server-side — see
# app.services.auth_service.register_user. UserCreate never accepts a role
# field from the client, so there is no way to self-assign a privileged
# role at signup.
DEFAULT_ROLE: str = Role.CANDIDATE.value
