"""Admission leases shared across processes, with expiry after crashes."""
import logging
import uuid
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException

from app.core.config import settings
from app.core.data_scope import DataScope
from app.core.dependencies import get_current_user, get_data_scope, get_token_store
from app.models.user import User
from app.services.token_store import TokenStore, TokenStoreUnavailable

logger = logging.getLogger(__name__)


def slot(
    store: TokenStore, resource: str, user_id: uuid.UUID, scope: DataScope,
    global_limit: int, user_limit: int, ttl: int,
) -> Iterator[None]:
    keys = [f"limits:{resource}:global", f"limits:{resource}:user:{user_id}"]
    limits = [global_limit, user_limit]
    if scope.demo_session_id:
        keys.append(f"limits:{resource}:demo:{scope.demo_session_id}")
        limits.append(1 if resource == "generation" else 2)
    token = str(uuid.uuid4())
    if not store.acquire_slots(keys, limits, token, ttl):
        raise HTTPException(
            429, "Too many active requests. Please try again shortly.",
            headers={"Retry-After": "2"},
        )
    try:
        yield
    finally:
        try:
            store.release_slots(keys, token)
        except TokenStoreUnavailable:
            logger.warning("limits.lease_release_pending_expiry")


def generation_slot(
    user: Annotated[User, Depends(get_current_user)],
    store: Annotated[TokenStore, Depends(get_token_store)],
    scope: Annotated[DataScope, Depends(get_data_scope)],
):
    yield from slot(
        store, "generation", user.id, scope,
        settings.generation_concurrency_global,
        settings.generation_concurrency_per_user, 900,
    )


def sse_slot(
    user: Annotated[User, Depends(get_current_user)],
    store: Annotated[TokenStore, Depends(get_token_store)],
    scope: Annotated[DataScope, Depends(get_data_scope)],
):
    # All server document streams rotate within 240 seconds.
    yield from slot(
        store, "sse", user.id, scope, settings.sse_concurrency_global,
        settings.sse_concurrency_per_user, 300,
    )
