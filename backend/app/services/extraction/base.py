from pathlib import Path
from typing import Protocol

from app.services.extraction.types import ExtractedSource


class SourceExtractionService(Protocol):
    def extract(self, file_path: Path) -> ExtractedSource:
        ...
