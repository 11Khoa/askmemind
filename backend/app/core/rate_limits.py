"""Shared Redis limits across API processes; authenticated limits use user IDs.

Only use the ASGI peer address for anonymous requests. Forwarded headers must be
validated by a trusted proxy/Uvicorn configuration, never parsed here.
"""
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from app.core.config import settings
from app.core.dependencies import get_current_user, get_token_store
from app.core.security import hash_token
from app.models.user import User
from app.services.token_store import TokenStore


def enforce_limit(store: TokenStore, key: str, limit: int, window: int) -> None:
    if not store.allow_request(key, limit, window):
        raise HTTPException(
            status_code=429,
            detail="Too many requests",
            headers={"Retry-After": str(window)},
        )


def limit_login(request: Request, store: Annotated[TokenStore, Depends(get_token_store)]) -> None:
    peer = request.client.host if request.client else "unknown"
    enforce_limit(store, f"login:ip:{hash_token(peer)}", settings.login_requests_per_minute, 60)


def limit_registration(request: Request, store: Annotated[TokenStore, Depends(get_token_store)]) -> None:
    peer = request.client.host if request.client else "unknown"
    enforce_limit(store, f"register:ip:{hash_token(peer)}", settings.register_requests_per_hour, 3600)


def limit_questions(
    user: Annotated[User, Depends(get_current_user)],
    store: Annotated[TokenStore, Depends(get_token_store)],
) -> None:
    enforce_limit(store, f"questions:user:{user.id}", settings.question_requests_per_minute, 60)


def limit_uploads(
    user: Annotated[User, Depends(get_current_user)],
    store: Annotated[TokenStore, Depends(get_token_store)],
) -> None:
    enforce_limit(store, f"uploads:user:{user.id}", settings.upload_requests_per_hour, 3600)
