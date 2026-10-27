from pathlib import Path
from typing import Protocol
from typing import Any

from app.services.extraction.types import ExtractedSource


class ExtractionCheckpoint(Protocol):
    def begin(self, fingerprint: str, total: int) -> dict[int, dict[str, Any]]: ...
    def save(self, page_number: int, text: str, metadata: dict) -> None: ...
    def report(self, **values: Any) -> None: ...


class SourceExtractionService(Protocol):
    def extract(self, file_path: Path, *, checkpoint: ExtractionCheckpoint | None = None) -> ExtractedSource:
        ...
