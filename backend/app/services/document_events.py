import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import redis
import redis.asyncio as async_redis
from starlette.requests import Request

from app.core.config import settings


class DocumentEventBroker:
    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url

    def _channel(self, user_id: uuid.UUID | str) -> str:
        return f'document-events:{user_id}'

    def publish(self, user_id: uuid.UUID | str, payload: dict[str, Any]) -> None:
        client = redis.Redis.from_url(self.redis_url)
        try:
            client.publish(
                self._channel(user_id),
                json.dumps(payload, default=str),
            )
        finally:
            client.close()

    async def stream(
        self,
        user_id: uuid.UUID | str,
        request: Request,
    ) -> AsyncIterator[str]:
        client = async_redis.Redis.from_url(self.redis_url)
        pubsub = client.pubsub()
        await pubsub.subscribe(self._channel(user_id))

        try:
            yield ': connected\n\n'
            while not await request.is_disconnected():
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=15,
                )
                if message is None:
                    yield ': keep-alive\n\n'
                    continue

                data = message.get('data')
                if isinstance(data, bytes):
                    data = data.decode('utf-8')

                yield f'event: document_status\ndata: {data}\n\n'
        finally:
            await pubsub.unsubscribe(self._channel(user_id))
            await pubsub.close()
            await client.aclose()


document_event_broker = DocumentEventBroker(redis_url=settings.redis_url)
