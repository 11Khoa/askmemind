from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import settings
from app.core.dependencies import get_auth_service, get_current_user
from app.schemas.user import UserCreate, UserRead, UserLogin, TokenResponse
from app.services.auth_service import AuthService
from app.models.user import User

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register_user(
    payload: UserCreate,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    if settings.enable_registration is False:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is currently disabled.",
        )

    try:
        return auth_service.register_user(
            email=payload.email,
            password=payload.password,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error


@router.post("/login", response_model=TokenResponse)
def login_user(
    payload: UserLogin,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    try:
        return auth_service.login_user(
            email=payload.email,
            password=payload.password,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(error),
        ) from error


@router.get("/me", response_model=UserRead)
def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
):
    return current_user