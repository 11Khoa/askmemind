import json
import logging
import re
import sys
import uuid
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from typing import Any


_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_user_id: ContextVar[str | None] = ContextVar("user_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }

        request_id = _request_id.get()
        user_id = _user_id.get()
        if request_id is not None:
            payload["request_id"] = request_id
        if user_id is not None:
            payload["user_id"] = user_id

        event_data = getattr(record, "event_data", None)
        if isinstance(event_data, dict):
            payload.update(event_data)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str, ensure_ascii=True)


def configure_logging(level: str = "INFO") -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(level.upper())

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root_logger.handlers.clear()
    root_logger.addHandler(handler)


def start_request_context(request_id: str | None = None) -> tuple[Token, Token]:
    normalized_request_id = normalize_request_id(request_id)
    return (
        _request_id.set(normalized_request_id),
        _user_id.set(None),
    )


def finish_request_context(tokens: tuple[Token, Token]) -> None:
    request_id_token, user_id_token = tokens
    _user_id.reset(user_id_token)
    _request_id.reset(request_id_token)


def bind_user_id(user_id: uuid.UUID) -> None:
    _user_id.set(str(user_id))


def get_request_id() -> str | None:
    return _request_id.get()


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    **event_data: Any,
) -> None:
    logger.log(
        level,
        event,
        extra={"event_data": event_data},
    )


def normalize_request_id(request_id: str | None) -> str:
    if request_id is not None and _REQUEST_ID_PATTERN.fullmatch(request_id):
        return request_id
    return str(uuid.uuid4())
