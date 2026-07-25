from enum import StrEnum
from typing import Literal

ChatRole = Literal["user", "assistant", "system"]


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
