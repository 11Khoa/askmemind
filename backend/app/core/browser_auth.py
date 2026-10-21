from datetime import datetime, timezone

from fastapi import HTTPException, Request, Response

from app.core.config import settings
from app.schemas.user import TokenResponse

CSRF_HEADER = "X-CSRF-Protection"
CSRF_HEADER_VALUE = "1"


def require_browser_csrf(request: Request) -> None:
    # No Referer/JSON-body fallback: even login must prove a trusted browser origin.
    origins = request.headers.getlist("origin")
    csrf_headers = request.headers.getlist(CSRF_HEADER)
    if (
        len(origins) != 1
        or origins[0] not in settings.csrf_trusted_origins
        or csrf_headers != [CSRF_HEADER_VALUE]
    ):
        raise HTTPException(status_code=403, detail="CSRF validation failed")


def require_json_token_client(request: Request) -> None:
    if not settings.auth_json_tokens_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    # Native/CLI flow accepts explicit body credentials only, never browser cookies.
    if any(name in request.headers for name in ("origin", "sec-fetch-site", "cookie")):
        raise HTTPException(
            status_code=403,
            detail="JSON token endpoints are for non-browser clients only",
        )


def read_refresh_cookie(request: Request) -> str:
    token = request.cookies.get(settings.auth_refresh_cookie_name)
    if token is None or not 32 <= len(token) <= 256:
        raise ValueError("Invalid or expired refresh token")
    return token


def set_refresh_cookie(response: Response, tokens: TokenResponse) -> None:
    # Cookie expiry follows the original DB session, including after rotation.
    expires = tokens.refresh_expires_at.astimezone(timezone.utc).replace(microsecond=0)
    remaining = max(0, int((expires - datetime.now(timezone.utc)).total_seconds()))
    response.set_cookie(
        key=settings.auth_refresh_cookie_name,
        value=tokens.refresh_token,
        max_age=remaining,
        expires=expires,
        path=settings.auth_refresh_cookie_path,
        secure=settings.auth_refresh_cookie_secure,
        httponly=True,
        samesite=settings.auth_refresh_cookie_samesite,
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.auth_refresh_cookie_name,
        path=settings.auth_refresh_cookie_path,
        secure=settings.auth_refresh_cookie_secure,
        httponly=True,
        samesite=settings.auth_refresh_cookie_samesite,
    )
