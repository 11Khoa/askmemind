"""Optional real Redis checks; CI supplies AUTH_TEST_REDIS_URL."""

import os
from uuid import uuid4

import pytest
from redis import Redis

from app.core.security import create_access_token, decode_access_token
from app.services.token_store import TokenStore


@pytest.mark.skipif(
    not os.getenv("AUTH_TEST_REDIS_URL"), reason="Requires isolated test Redis"
)
def test_real_redis_blacklist_and_rate_limit():
    client = Redis.from_url(os.environ["AUTH_TEST_REDIS_URL"])
    store = TokenStore(client)
    payload = decode_access_token(create_access_token(str(uuid4())))
    rate_key = f"integration:{uuid4()}"
    try:
        assert not store.is_revoked(payload.jti)
        store.revoke_access(payload)
        assert store.is_revoked(payload.jti)
        assert client.ttl(f"auth:revoked:{payload.jti}") > 0
        assert store.allow_request(rate_key, limit=1, window=60)
        assert not store.allow_request(rate_key, limit=1, window=60)
        assert 0 < client.ttl(f"auth:rate:{rate_key}") <= 60
    finally:
        client.delete(f"auth:revoked:{payload.jti}", f"auth:rate:{rate_key}")
        client.close()


@pytest.mark.skipif(
    not os.getenv("AUTH_TEST_REDIS_URL"), reason="Requires isolated test Redis"
)
def test_logout_blocks_protected_endpoint_with_real_redis(auth_client, auth_tokens):
    from app.core.dependencies import get_token_store
    from app.main import app

    client = Redis.from_url(os.environ["AUTH_TEST_REDIS_URL"])
    app.dependency_overrides[get_token_store] = lambda: TokenStore(client)
    headers = {"Authorization": f"Bearer {auth_tokens['access_token']}"}
    payload = decode_access_token(auth_tokens["access_token"])
    try:
        assert auth_client.get("/auth/me", headers=headers).status_code == 200
        assert (
            auth_client.post(
                "/auth/logout",
                headers=headers,
                json={"refresh_token": auth_tokens["refresh_token"]},
            ).status_code
            == 204
        )
        assert auth_client.get("/auth/me", headers=headers).status_code == 401
    finally:
        client.delete(f"auth:revoked:{payload.jti}")
        client.close()
