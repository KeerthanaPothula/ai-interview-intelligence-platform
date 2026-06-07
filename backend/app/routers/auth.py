from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.security import create_access_token
from app.database import get_db
from app.models.user import User
from app.schemas.auth import Token, UserCreate, UserResponse
from app.services.auth_service import authenticate_user, register_user

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user account",
)
def register(
    user_data: UserCreate,
    db: Session = Depends(get_db),
) -> User:
    return register_user(db, user_data)


@router.post(
    "/login",
    response_model=Token,
    summary="Exchange email + password for a JWT access token",
)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> Token:
    """
    Accepts standard OAuth2 form fields:
      - username  (we treat this as the email address)
      - password

    Returns a Bearer token valid for ACCESS_TOKEN_EXPIRE_MINUTES minutes.
    The /docs UI uses this endpoint automatically to issue tokens.
    """
    user = authenticate_user(db, form_data.username, form_data.password)
    if user is None:
        # Intentionally vague — do not reveal whether the email exists.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(data={"sub": user.email})
    return Token(access_token=token)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Return the currently authenticated user",
)
def get_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
