import json
import uuid
import logging
from time import monotonic
import anyio
from collections.abc import AsyncIterator
from typing import Any

import redis
import redis.asyncio as async_redis
from starlette.requests import Request

from app.core.config import settings

logger = logging.getLogger(__name__)


class DocumentEventBroker:
    admin_channel = "admin:document-events"
    def __init__(self, redis_url: str, heartbeat_seconds: float = 15,
                 max_stream_seconds: float = 240) -> None:
        self.redis_url = redis_url
        self.heartbeat_seconds = heartbeat_seconds
        self.max_stream_seconds = max_stream_seconds

    def _channel(self, user_id: uuid.UUID | str) -> str:
        return f"document-events:{user_id}"

    def publish(self, user_id: uuid.UUID | str, payload: dict[str, Any]) -> None:
        client = redis.Redis.from_url(
            self.redis_url, socket_timeout=2, socket_connect_timeout=2
        )
        try:
            client.publish(
                self._channel(user_id),
                json.dumps(payload, default=str),
            )
            # The global channel carries processing metadata only, never source
            # text, paths or raw provider errors. Only the admin route subscribes.
            fields = ("document_id", "status", "page_count", "updated_at", "processing_attempt_id")
            progress_fields = ("stage", "completed_pages", "total_pages", "current_page", "reused_pages",
                               "completed_chunks", "total_chunks", "failed_stage", "error_code", "started_at", "finished_at")
            admin_payload = {key: payload[key] for key in fields if key in payload}
            admin_payload["user_id"] = str(user_id)
            admin_payload["error_message"] = None
            progress = payload.get("processing_progress")
            if isinstance(progress, dict):
                admin_payload["processing_progress"] = {key: progress[key] for key in progress_fields if key in progress}
            try:
                client.publish(self.admin_channel, json.dumps(admin_payload, default=str))
            except redis.RedisError:
                logger.warning("document.admin_events.publish_failed")
        finally:
            client.close()

    def stream(
        self,
        user_id: uuid.UUID | str,
        request: Request,
    ) -> AsyncIterator[str]:
        return self._stream_channel(self._channel(user_id), request)

    def stream_admin(self, request: Request) -> AsyncIterator[str]:
        return self._stream_channel(self.admin_channel, request)

    async def _stream_channel(self, channel: str, request: Request) -> AsyncIterator[str]:
        client = async_redis.Redis.from_url(
            self.redis_url, socket_connect_timeout=5, socket_timeout=30,
        )
        pubsub = client.pubsub()
        try:
            await pubsub.subscribe(channel)
            deadline = monotonic() + self.max_stream_seconds
            yield ": connected\n\n"
            while monotonic() < deadline and not await request.is_disconnected():
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=min(self.heartbeat_seconds, max(0, deadline - monotonic())),
                )
                if message is None:
                    yield ": keep-alive\n\n"
                    continue

                data = message.get("data")
                if isinstance(data, bytes):
                    data = data.decode("utf-8")

                yield f"event: document_status\ndata: {data}\n\n"
        except (redis.RedisError, OSError) as error:
            logger.warning("document.events.disconnected", extra={"event_data": {
                "error_type": type(error).__name__,
            }})
            # Close normally. Clients reconnect with backoff and resynchronize;
            # no provider/Redis details belong in a browser error banner.
        finally:
            with anyio.move_on_after(5, shield=True):
                for cleanup in (pubsub.aclose, client.aclose):
                    try:
                        await cleanup()
                    except (redis.RedisError, OSError):
                        logger.warning("document.events.cleanup_failed")


document_event_broker = DocumentEventBroker(redis_url=settings.redis_url)
