import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.rate_limits import limit_login, limit_registration
from app.core.browser_auth import (
    clear_refresh_cookie,
    read_refresh_cookie,
    require_browser_csrf,
    require_json_token_client,
    set_refresh_cookie,
)
from app.core.dependencies import (
    get_auth_service,
    get_current_user,
    get_current_access_payload,
    get_token_store,
    get_password_reset_service,
)
from app.core.logging import get_request_id, log_event
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
    AccessTokenResponse,
    RefreshTokenRequest,
)
from app.schemas.user import ForgotPasswordRequest, ResetPasswordRequest
from app.services.auth_service import AuthService
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)


@router.post(
    "/register", response_model=UserRead, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limit_registration)],
)
def register_user(
    payload: UserCreate,
    request: Request,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    if settings.enable_registration is False:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is currently disabled.",
        )

    try:
        user = auth_service.register_user(
            email=payload.email,
            password=payload.password,
        )
        request.state.actor_id = user.id
        return user
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error


@router.post(
    "/login",
    response_model=AccessTokenResponse,
    dependencies=[Depends(require_browser_csrf), Depends(limit_login)],
)
def login_user(
    payload: UserLogin,
    request: Request,
    response: Response,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    try:
        tokens = auth_service.login_user(
            email=payload.email,
            password=payload.password,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(error),
        ) from error
    request.state.actor_id = getattr(auth_service, "authenticated_user_id", None)
    set_refresh_cookie(response, tokens)
    return AccessTokenResponse(access_token=tokens.access_token)


@router.get("/me", response_model=UserRead)
def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
):
    return current_user


def invalid_refresh_cookie_response(detail: str) -> JSONResponse:
    response = JSONResponse(status_code=401, content={"detail": detail})
    clear_refresh_cookie(response)
    return response


@router.post(
    "/refresh",
    response_model=AccessTokenResponse,
    dependencies=[Depends(require_browser_csrf)],
)
def refresh_tokens(
    request: Request,
    response: Response,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    try:
        tokens = auth_service.refresh(read_refresh_cookie(request))
    except ValueError as error:
        return invalid_refresh_cookie_response(str(error))
    set_refresh_cookie(response, tokens)
    return AccessTokenResponse(access_token=tokens.access_token)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_browser_csrf)],
)
def logout(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    access_payload: Annotated[AccessTokenPayload, Depends(get_current_access_payload)],
    token_store: Annotated[TokenStore, Depends(get_token_store)],
):
    try:
        auth_service.logout(current_user.id, read_refresh_cookie(request))
    except ValueError as error:
        return invalid_refresh_cookie_response(str(error))
    token_store.revoke_access(access_payload)
    response = Response(status_code=204)
    clear_refresh_cookie(response)
    return response


@router.post(
    "/token/login",
    response_model=TokenResponse,
    dependencies=[Depends(require_json_token_client), Depends(limit_login)],
)
def login_json_client(
    payload: UserLogin,
    request: Request,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    try:
        tokens = auth_service.login_user(payload.email, payload.password)
        request.state.actor_id = getattr(auth_service, "authenticated_user_id", None)
        return tokens
    except ValueError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error


@router.post(
    "/token/refresh",
    response_model=TokenResponse,
    dependencies=[Depends(require_json_token_client)],
)
def refresh_json_client(
    payload: RefreshTokenRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    try:
        return auth_service.refresh(payload.refresh_token)
    except ValueError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error


@router.post(
    "/token/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_json_token_client)],
)
def logout_json_client(
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
        log_event(
            logger,
            logging.ERROR,
            "auth.password_reset.unconfigured",
            request_id=get_request_id(),
            smtp_host_configured=bool(settings.smtp_host),
            smtp_sender_configured=bool(settings.smtp_from_email),
            reset_url_configured=settings.password_reset_url is not None,
            reset_url_scheme=(
                settings.password_reset_url.scheme
                if settings.password_reset_url is not None
                else None
            ),
        )
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
    except Exception as error:
        log_event(
            logger,
            logging.ERROR,
            "auth.password_reset.enqueue_failed",
            request_id=get_request_id(),
            error_type=type(error).__name__,
        )
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
