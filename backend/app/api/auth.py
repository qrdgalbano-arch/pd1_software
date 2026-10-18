import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    verify_password,
)
from app.database.session import get_db
from app.models import User
from app.schemas.auth import RefreshTokenRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/login", response_model=TokenResponse)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> TokenResponse:
    user = db.scalar(
        select(User).where(User.email == form_data.username)
    )

    if not user or not verify_password(
        form_data.password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    return TokenResponse(
        access_token=create_access_token(
            user_id=user.id,
            role=user.role.value,
        ),
        refresh_token=create_refresh_token(user_id=user.id),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh_tokens(
    request: RefreshTokenRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate refresh token",
    )

    try:
        payload = jwt.decode(
            request.refresh_token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        user_id = payload.get("sub")
        token_type = payload.get("type")

        if user_id is None or token_type != "refresh":
            raise credentials_exception

        user = db.get(User, int(user_id))
    except (jwt.PyJWTError, ValueError):
        raise credentials_exception

    if user is None or not user.is_active:
        raise credentials_exception

    return TokenResponse(
        access_token=create_access_token(
            user_id=user.id,
            role=user.role.value,
        ),
        refresh_token=create_refresh_token(user_id=user.id),
    )


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)) -> dict:
    return {
        "id": current_user.id,
        "full_name": current_user.full_name,
        "email": current_user.email,
        "role": current_user.role.value,
    }
