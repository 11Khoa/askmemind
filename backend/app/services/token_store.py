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

    def allow_request(self, key: str, limit: int, window: int) -> bool:
        script = """
        local count = redis.call('INCR', KEYS[1])
        if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
        return count
        """
        try:
            return self.client.eval(script, 1, f"auth:rate:{key}", window) <= limit
        except RedisError as error:
            raise TokenStoreUnavailable() from error


    def acquire_slots(self, keys, limits, token, ttl):
        script = """
        local t=redis.call('TIME')
        local now=tonumber(t[1])+tonumber(t[2])/1000000
        for i,key in ipairs(KEYS) do
            redis.call('ZREMRANGEBYSCORE',key,'-inf',now)
            if redis.call('ZCARD',key)>=tonumber(ARGV[i+2]) then return 0 end
        end
        for i,key in ipairs(KEYS) do
            redis.call('ZADD',key,now+tonumber(ARGV[2]),ARGV[1])
            redis.call('EXPIRE',key,tonumber(ARGV[2])+1)
        end
        return 1
        """
        try:
            return bool(self.client.eval(script,len(keys),*keys,token,ttl,*limits))
        except RedisError as error:
            raise TokenStoreUnavailable() from error

    def release_slots(self, keys, token):
        try:
            with self.client.pipeline() as pipeline:
                for key in keys: pipeline.zrem(key,token)
                pipeline.execute()
        except RedisError as error:
            raise TokenStoreUnavailable() from error
