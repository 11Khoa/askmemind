from datetime import datetime, timezone
from math import ceil

from redis import Redis
from redis.exceptions import RedisError

from app.core.security import AccessTokenPayload


class TokenStoreUnavailable(Exception):
    pass


class TokenStore:
    def __init__(self, client: Redis):
        self.client = client

    def is_revoked(self, jti: str) -> bool:
        try:
            return bool(self.client.exists(f"auth:revoked:{jti}"))
        except RedisError as error:
            raise TokenStoreUnavailable() from error

    def revoke_access(self, payload: AccessTokenPayload) -> None:
        ttl = ceil((payload.expires_at - datetime.now(timezone.utc)).total_seconds())
        if ttl <= 0:
            return
        try:
            self.client.set(f"auth:revoked:{payload.jti}", "1", ex=ttl)
        except RedisError as error:
            raise TokenStoreUnavailable() from error
