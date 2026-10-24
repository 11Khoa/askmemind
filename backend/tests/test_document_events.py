import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import redis

from app.services.document_events import DocumentEventBroker
from app.services import document_events


def clients(monkeypatch):
    pubsub = SimpleNamespace(subscribe=AsyncMock(), get_message=AsyncMock(), aclose=AsyncMock())
    client = SimpleNamespace(pubsub=Mock(return_value=pubsub), aclose=AsyncMock())
    monkeypatch.setattr(document_events.async_redis.Redis, "from_url", Mock(return_value=client))
    return client, pubsub


def test_stream_heartbeats_events_and_cleanup(monkeypatch):
    client, pubsub = clients(monkeypatch)
    request = SimpleNamespace(is_disconnected=AsyncMock(side_effect=[False, False, True]))
    pubsub.get_message.side_effect = [None, {"data": b'{"status":"ready"}'}]
    monkeypatch.setattr(document_events, "monotonic", lambda: 0)
    async def collect():
        return [frame async for frame in DocumentEventBroker("redis://unused").stream(uuid4(), request)]
    assert asyncio.run(collect()) == [": connected\n\n", ": keep-alive\n\n", 'event: document_status\ndata: {"status":"ready"}\n\n']
    assert pubsub.get_message.await_args.kwargs["timeout"] == 15
    pubsub.aclose.assert_awaited_once()
    client.aclose.assert_awaited_once()


def test_stream_rotates_at_bounded_lifetime(monkeypatch):
    client, pubsub = clients(monkeypatch)
    clock = {"now": 0}
    monkeypatch.setattr(document_events, "monotonic", lambda: clock["now"])
    async def message(**kwargs):
        clock["now"] = 30
        return None
    pubsub.get_message.side_effect = message
    request = SimpleNamespace(is_disconnected=AsyncMock(return_value=False))
    async def collect():
        return [frame async for frame in DocumentEventBroker("redis://unused", max_stream_seconds=30).stream(uuid4(), request)]
    assert len(asyncio.run(collect())) == 2
    pubsub.get_message.assert_awaited_once()
    client.aclose.assert_awaited_once()


def test_subscribe_failure_still_closes_both_redis_handles(monkeypatch):
    client, pubsub = clients(monkeypatch)
    pubsub.subscribe.side_effect = redis.ConnectionError("private connection details")
    request = SimpleNamespace(is_disconnected=AsyncMock(return_value=False))
    async def collect():
        return [frame async for frame in DocumentEventBroker("redis://unused").stream(uuid4(), request)]
    assert asyncio.run(collect()) == []
    pubsub.aclose.assert_awaited_once()
    client.aclose.assert_awaited_once()


def test_cleanup_failure_does_not_skip_client_close(monkeypatch):
    client, pubsub = clients(monkeypatch)
    pubsub.get_message.side_effect = redis.ConnectionError("unavailable")
    pubsub.aclose.side_effect = redis.ConnectionError("already disconnected")
    request = SimpleNamespace(is_disconnected=AsyncMock(return_value=False))
    async def collect():
        return [frame async for frame in DocumentEventBroker("redis://unused").stream(uuid4(), request)]
    assert asyncio.run(collect()) == [": connected\n\n"]
    client.aclose.assert_awaited_once()


def test_cancelling_stream_releases_subscription(monkeypatch):
    client, pubsub = clients(monkeypatch)
    request = SimpleNamespace(is_disconnected=AsyncMock(return_value=False))
    async def cancel():
        stream = DocumentEventBroker("redis://unused").stream(uuid4(), request)
        await anext(stream)
        await stream.aclose()
    asyncio.run(cancel())
    pubsub.aclose.assert_awaited_once()
    client.aclose.assert_awaited_once()


def test_endpoint_releases_database_before_waiting_for_events():
    from app.routers.document import stream_document_events
    db = Mock()
    response = asyncio.run(stream_document_events(Mock(), SimpleNamespace(id=uuid4()), db))
    db.close.assert_called_once()
    assert response.headers["Cache-Control"] == "no-cache, no-transform"
    assert response.headers["X-Accel-Buffering"] == "no"
