from dataclasses import dataclass, field
from typing import Any

from app.services.extraction.types import ExtractedSource, ExtractedTextUnit


@dataclass(frozen=True)
class TextChunk:
    chunk_index: int
    content: str
    page_number: int | None = None
    start_char: int | None = None
    end_char: int | None = None
    start_time_seconds: float | None = None
    end_time_seconds: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ChunkingService:
    def __init__(self, chunk_size: int = 1000, overlap: int = 200) -> None:
        self._validate_config(chunk_size=chunk_size, overlap=overlap)

        self.chunk_size = chunk_size
        self.overlap = overlap

    def _validate_config(self, chunk_size: int, overlap: int) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be greater than 0")

        if overlap < 0:
            raise ValueError("overlap must be greater than or equal to 0")

        if overlap >= chunk_size:
            raise ValueError("overlap must be smaller than chunk_size")

    def chunk_source(self, source: ExtractedSource) -> list[TextChunk]:
        chunks: list[TextChunk] = []
        next_chunk_index = 0

        for unit in source.units:
            unit_chunks = self._chunk_text_unit(
                unit=unit,
                start_chunk_index=next_chunk_index,
            )

            chunks.extend(unit_chunks)
            next_chunk_index += len(unit_chunks)

        return chunks

    def _chunk_text_unit(
        self,
        unit: ExtractedTextUnit,
        start_chunk_index: int,
    ) -> list[TextChunk]:
        if not unit.text.strip():
            return []

        chunks: list[TextChunk] = []
        text = unit.text
        text_length = len(text)
        step = self.chunk_size - self.overlap

        start = 0
        local_chunk_count = 0

        while start < text_length:
            end = min(start + self.chunk_size, text_length)
            content = text[start:end]

            chunks.append(
                TextChunk(
                    chunk_index=start_chunk_index + local_chunk_count,
                    content=content,
                    page_number=unit.page_number,
                    start_char=start,
                    end_char=end,
                    start_time_seconds=unit.start_time_seconds,
                    end_time_seconds=unit.end_time_seconds,
                    metadata=dict(unit.metadata),
                )
            )

            if end == text_length:
                break

            start += step
            local_chunk_count += 1

        return chunks
