import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4
import redis
import os
import pytest

from app.services.document_events import DocumentEventBroker


def test_publish_fans_out_metadata_without_leaking_document_text_or_errors(monkeypatch):
    client = Mock()
    monkeypatch.setattr("app.services.document_events.redis.Redis.from_url", Mock(return_value=client))
    broker = DocumentEventBroker("redis://unused")
    owner = uuid4()
    payload = {"document_id": str(uuid4()), "status": "processing", "page_count": 144,
               "error_message": "private provider detail", "file_path": "/private.pdf", "text": "private page text",
               "processing_progress": {"stage": "ocr", "current_page": 23, "text": "private text"}}
    broker.publish(owner, payload)
    user_channel, user_data = client.publish.call_args_list[0].args
    admin_channel, admin_data = client.publish.call_args_list[1].args
    assert user_channel == f"document-events:{owner}"
    assert json.loads(user_data) == payload
    assert admin_channel == broker.admin_channel
    admin = json.loads(admin_data)
    assert admin["user_id"] == str(owner)
    assert admin["processing_progress"] == {"stage": "ocr", "current_page": 23}
    assert "private" not in admin_data
    client.close.assert_called_once()


def test_admin_stream_subscribes_to_only_global_channel_and_closes_resources(monkeypatch):
    pubsub = SimpleNamespace(subscribe=AsyncMock(), get_message=AsyncMock(return_value={"data": b'{"status":"ready"}'}), aclose=AsyncMock())
    client = SimpleNamespace(pubsub=Mock(return_value=pubsub), aclose=AsyncMock())
    monkeypatch.setattr("app.services.document_events.async_redis.Redis.from_url", Mock(return_value=client))
    request = SimpleNamespace(is_disconnected=AsyncMock(side_effect=[False, True]))
    broker = DocumentEventBroker("redis://unused")
    async def collect():
        return [frame async for frame in broker.stream_admin(request)]
    frames = asyncio.run(collect())
    pubsub.subscribe.assert_awaited_once_with(broker.admin_channel)
    assert frames == [": connected\n\n", 'event: document_status\ndata: {"status":"ready"}\n\n']
    pubsub.aclose.assert_awaited_once()
    client.aclose.assert_awaited_once()


def test_admin_publish_failure_does_not_break_private_notifications(monkeypatch):
    client = Mock()
    client.publish.side_effect = [1, redis.ConnectionError("unavailable")]
    monkeypatch.setattr("app.services.document_events.redis.Redis.from_url", Mock(return_value=client))
    DocumentEventBroker("redis://unused").publish(uuid4(), {"status": "ready"})
    assert client.publish.call_count == 2
    client.close.assert_called_once()


def test_admin_route_releases_database_session_and_disables_proxy_buffering(monkeypatch):
    from app.routers.admin import document_events
    stream = Mock(return_value=object())
    monkeypatch.setattr("app.routers.admin.document_event_broker.stream_admin", stream)
    db = Mock()
    request = Mock()
    response = asyncio.run(document_events(request, SimpleNamespace(role="admin"), db))
    db.close.assert_called_once()
    stream.assert_called_once_with(request)
    assert response.headers["x-accel-buffering"] == "no"
    assert response.headers["content-type"].startswith("text/event-stream")


@pytest.mark.skipif(not os.getenv("AUTH_TEST_REDIS_URL"), reason="Requires isolated test Redis")
def test_real_redis_admin_receives_multiple_users_without_cross_user_delivery():
    client = redis.Redis.from_url(os.environ["AUTH_TEST_REDIS_URL"])
    broker = DocumentEventBroker(os.environ["AUTH_TEST_REDIS_URL"])
    broker.admin_channel = f"test-admin-document-events:{uuid4()}"
    owner, other = uuid4(), uuid4()
    with client, client.pubsub() as private, client.pubsub() as global_stream:
        private.subscribe(broker._channel(owner))
        global_stream.subscribe(broker.admin_channel)
        # Wait for subscription acknowledgments before publishing.
        assert private.get_message(timeout=2)["type"] == "subscribe"
        assert global_stream.get_message(timeout=2)["type"] == "subscribe"
        broker.publish(other, {"document_id": "other-doc", "status": "processing"})
        global_event = global_stream.get_message(ignore_subscribe_messages=True, timeout=2)
        assert json.loads(global_event["data"])["user_id"] == str(other)
        assert private.get_message(ignore_subscribe_messages=True, timeout=0.1) is None
        broker.publish(owner, {"document_id": "own-doc", "status": "ready"})
        assert json.loads(private.get_message(ignore_subscribe_messages=True, timeout=2)["data"])["document_id"] == "own-doc"
        assert json.loads(global_stream.get_message(ignore_subscribe_messages=True, timeout=2)["data"])["document_id"] == "own-doc"
