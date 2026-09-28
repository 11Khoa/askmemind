import json
import logging
import uuid

from app.core.logging import (
    JsonFormatter,
    bind_user_id,
    finish_request_context,
    normalize_request_id,
    start_request_context,
)


def test_json_formatter_includes_request_user_and_event_fields() -> None:
    request_id = "request-123"
    user_id = uuid.uuid4()
    tokens = start_request_context(request_id=request_id)

    try:
        bind_user_id(user_id)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="rag.completed",
            args=(),
            exc_info=None,
        )
        record.event_data = {
            "duration_ms": 12.5,
            "retrieved_chunks": 5,
        }

        payload = json.loads(JsonFormatter().format(record))
    finally:
        finish_request_context(tokens)

    assert payload["event"] == "rag.completed"
    assert payload["request_id"] == request_id
    assert payload["user_id"] == str(user_id)
    assert payload["duration_ms"] == 12.5
    assert payload["retrieved_chunks"] == 5


def test_normalize_request_id_rejects_unsafe_values() -> None:
    assert normalize_request_id("valid-request_123") == "valid-request_123"

    generated_request_id = normalize_request_id("invalid request\nvalue")

    assert uuid.UUID(generated_request_id)
