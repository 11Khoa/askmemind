from pathlib import Path

import fitz

from app.services.extraction.types import (
    ExtractedSource,
    ExtractedTextUnit,
)


class PdfExtractionService:
    def extract(self, file_path: Path) -> ExtractedSource:
        units: list[ExtractedTextUnit] = []

        with fitz.open(file_path) as document:
            page_count = document.page_count

            for page_index in range(page_count):
                page = document.load_page(page_index)
                text = page.get_text().strip()

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
