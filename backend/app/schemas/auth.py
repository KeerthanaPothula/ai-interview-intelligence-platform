import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


class UserCreate(BaseModel):
    """Request body for POST /auth/register."""

    email: EmailStr
    # min_length enforced here so the error is caught before bcrypt
    # wastes CPU hashing a one-character password.
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(..., min_length=1, max_length=255)

    @field_validator("full_name")
    @classmethod
    def strip_and_reject_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("full_name cannot be blank or whitespace only.")
        return stripped


class OrganizationBrief(BaseModel):
    """Minimal organization info embedded in UserResponse — the full
    OrganizationResponse (with member counts) lives in app.schemas.admin
    and is only returned by the admin organization-management endpoints."""

    id: uuid.UUID
    name: str

    model_config = {"from_attributes": True}


class UserResponse(BaseModel):
    """Returned by register and /me endpoints. Never includes the password."""

    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: str
    organization: OrganizationBrief | None = None
    created_at: datetime

    # from_attributes=True allows Pydantic to read values from SQLAlchemy
    # ORM instances (attribute access) rather than only from dicts — reads
    # user.organization (the relationship) straight into OrganizationBrief.
    model_config = {"from_attributes": True}


class Token(BaseModel):
    """Returned by the login and refresh endpoints.

    refresh_token defaults to None so this schema also still matches the
    pre-Phase-3 login response shape for any client that only reads
    access_token/token_type.
    """

    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """Request body for POST /auth/refresh and POST /auth/logout."""

    refresh_token: str = Field(..., min_length=20, max_length=512)


class DetailResponse(BaseModel):
    """Generic {"detail": "..."} acknowledgement, e.g. for logout."""

    detail: str


class ForgotPasswordRequest(BaseModel):
    """Request body for POST /auth/forgot-password."""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Request body for POST /auth/reset-password."""

    token: str = Field(..., min_length=20, max_length=512)
    new_password: str = Field(..., min_length=8, max_length=128)


class ChangePasswordRequest(BaseModel):
    """Request body for POST /auth/change-password."""

    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)
