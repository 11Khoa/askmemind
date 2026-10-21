from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.core.config import settings
from app.core.dependencies import (
    get_auth_service,
    get_current_user,
    get_current_access_payload,
    get_token_store,
    get_password_reset_service,
)
from app.core.logging import get_request_id
from app.core.security import AccessTokenPayload, hash_token
from app.services.token_store import TokenStore
from app.services.password_reset_service import PasswordResetService
from app.services.reset_email_service import ResetEmailService
from app.tasks.password_reset import send_password_reset
from app.schemas.user import (
    UserCreate,
    UserRead,
    UserLogin,
    TokenResponse,
    RefreshTokenRequest,
)
from app.schemas.user import ForgotPasswordRequest, ResetPasswordRequest
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


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    token_store: Annotated[TokenStore, Depends(get_token_store)],
):
    if not ResetEmailService(settings).is_configured():
        raise HTTPException(
            status_code=503, detail="Password reset temporarily unavailable"
        )
    ip = request.client.host if request.client else "unknown"
    if not token_store.allow_request(f"forgot:ip:{hash_token(ip)}", 10, 3600):
        raise HTTPException(
            status_code=429, detail="Too many requests", headers={"Retry-After": "3600"}
        )
    message = {"message": "If the account exists, a password reset email will be sent."}
    if not token_store.allow_request(
        f"forgot:email:{hash_token(payload.email)}", 3, 3600
    ):
        return message
    try:
        # Queue both existing and unknown emails; account lookup happens in the worker.
        send_password_reset.apply_async(
            kwargs={"email": payload.email, "request_id": get_request_id()},
            kwargsrepr="<redacted>",
        )
    except Exception:
        raise HTTPException(
            status_code=503, detail="Password reset temporarily unavailable"
        ) from None
    return message


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    service: Annotated[PasswordResetService, Depends(get_password_reset_service)],
    token_store: Annotated[TokenStore, Depends(get_token_store)],
):
    ip = request.client.host if request.client else "unknown"
    if not token_store.allow_request(f"reset:ip:{hash_token(ip)}", 10, 60):
        raise HTTPException(
            status_code=429, detail="Too many requests", headers={"Retry-After": "60"}
        )
    try:
        service.reset(payload.token, payload.new_password)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return Response(status_code=204)
