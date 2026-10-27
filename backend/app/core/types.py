from enum import StrEnum
from typing import Literal

ChatRole = Literal["user", "assistant", "system"]


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    PROCESSING_FAILED = "processing_failed"
    CANCELLED = "cancelled"
    COMPLETED = "ready"
    FAILED = "processing_failed"
