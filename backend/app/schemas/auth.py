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


class UserResponse(BaseModel):
    """Returned by register and /me endpoints. Never includes the password."""

    id: uuid.UUID
    email: EmailStr
    full_name: str
    created_at: datetime

    # from_attributes=True allows Pydantic to read values from SQLAlchemy
    # ORM instances (attribute access) rather than only from dicts.
    model_config = {"from_attributes": True}


class Token(BaseModel):
    """Returned by the login endpoint."""

    access_token: str
    token_type: str = "bearer"
