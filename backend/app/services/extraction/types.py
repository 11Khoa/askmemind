from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ExtractedTextUnit:
    text: str
    page_number: int | None = None
    start_time_seconds: float | None = None
    end_time_seconds: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExtractedSource:
    source_type: str
    units: list[ExtractedTextUnit]
    metadata: dict[str, Any] = field(default_factory=dict)
