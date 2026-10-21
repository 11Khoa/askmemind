from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.core.config import settings
from app.core.dependencies import (
    get_auth_service, get_current_user, get_current_access_payload, get_token_store,
)
from app.core.security import AccessTokenPayload
from app.services.token_store import TokenStore
from app.schemas.user import UserCreate, UserRead, UserLogin, TokenResponse, RefreshTokenRequest
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


@router.post("/refresh", response_model=TokenResponse)
def refresh_tokens(
    payload: RefreshTokenRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    try:
        return auth_service.refresh(payload.refresh_token)
    except ValueError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    payload: RefreshTokenRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    access_payload: Annotated[AccessTokenPayload, Depends(get_current_access_payload)],
    token_store: Annotated[TokenStore, Depends(get_token_store)],
):
    try:
        auth_service.logout(current_user.id, payload.refresh_token)
    except ValueError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
    token_store.revoke_access(access_payload)
    return Response(status_code=204)
