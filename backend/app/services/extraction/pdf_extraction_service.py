from pathlib import Path

import fitz

from app.core.config import settings

from app.services.extraction.types import (
    ExtractedSource,
    ExtractedTextUnit,
)


class PdfExtractionService:
    def __init__(self, max_pages: int | None = None, max_text_characters: int | None = None):
        self.max_pages = max_pages if max_pages is not None else settings.max_pdf_pages
        self.max_text_characters = (
            max_text_characters if max_text_characters is not None
            else settings.max_pdf_text_characters
        )

    def extract(self, file_path: Path) -> ExtractedSource:
        units: list[ExtractedTextUnit] = []
        text_characters = 0

        with fitz.open(file_path) as document:
            page_count = document.page_count
            if page_count > self.max_pages:
                raise ValueError("PDF exceeds the configured page limit")

            for page_index in range(page_count):
                page = document.load_page(page_index)
                text = page.get_text().strip()
                text_characters += len(text)
                if text_characters > self.max_text_characters:
                    raise ValueError("PDF exceeds the configured extracted text limit")

                if not text:
                    continue

                units.append(
                    ExtractedTextUnit(
                        text=text,
                        page_number=page_index + 1,
                    )
                )

        if not units:
            raise ValueError("PDF does not contain extractable text")

        return ExtractedSource(
            source_type="pdf",
            units=units,
            metadata={"page_count": page_count},
        )
