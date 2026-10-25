from pathlib import Path
import logging
from time import monotonic

import fitz

from app.core.config import settings
from app.core.logging import log_event
from app.services.extraction.ocr_session import OCRSession

from app.services.extraction.types import (
    ExtractedSource,
    ExtractedTextUnit,
)

logger = logging.getLogger(__name__)


class PdfExtractionService:
    def __init__(self, max_pages: int | None = None, max_text_characters: int | None = None):
        self.max_pages = max_pages if max_pages is not None else settings.max_pdf_pages
        self.max_text_characters = (
            max_text_characters if max_text_characters is not None
            else settings.max_pdf_text_characters
        )

    def extract(self, file_path: Path) -> ExtractedSource:
        started = monotonic()
        session = OCRSession(file_path, settings, started + settings.pdf_ocr_document_timeout_seconds)
        try:
            return self._extract(file_path, session, started)
        finally:
            session.close()

    @staticmethod
    def _needs_ocr(page, text: str) -> bool:
        # Text PDFs remain on the fast path. A short header over a large scanned
        # image still needs OCR; render the whole page once to avoid duplicates.
        if not text:
            return bool(page.get_bboxlog())
        if len(text) >= 80:
            return False
        area = page.rect.get_area()
        return area > 0 and any(
            (fitz.Rect(image["bbox"]) & page.rect).get_area() / area >= 0.25
            for image in page.get_image_info()
        )

    def _extract(self, file_path: Path, session: OCRSession, started: float) -> ExtractedSource:
        units: list[ExtractedTextUnit] = []
        text_characters = 0
        ocr_pages = 0
        empty_ocr_pages = []
        with fitz.open(file_path) as document:
            page_count = document.page_count
            if page_count > self.max_pages:
                raise ValueError("PDF exceeds the configured page limit")

            for page_index in range(page_count):
                page = document.load_page(page_index)
                text = page.get_text().strip()
                metadata = {}
                if settings.pdf_ocr_enabled and self._needs_ocr(page, text):
                    ocr_pages += 1
                    if ocr_pages > settings.pdf_ocr_max_pages:
                        raise ValueError("PDF exceeds the configured OCR page limit. Split the PDF and retry.")
                    result = session.recognize(page_index, self.max_text_characters - text_characters)
                    # Prefer a complete OCR rendering over a partial text header.
                    # If OCR finds no reliable text, keep any existing native text.
                    if result["text"].strip():
                        text = result["text"].strip()
                        metadata = {"extraction_method": "ocr", "ocr_confidence": result["confidence"]}
                    else:
                        empty_ocr_pages.append(page_index + 1)
                text_characters += len(text)
                if text_characters > self.max_text_characters:
                    raise ValueError("PDF exceeds the configured extracted text limit")

                if not text:
                    continue

                units.append(
                    ExtractedTextUnit(
                        text=text,
                        page_number=page_index + 1,
                        metadata=metadata,
                    )
                )

        if not units:
            raise ValueError("PDF does not contain extractable text")

        log_event(logger, logging.INFO, "pdf.extraction.completed",
                  page_count=page_count, ocr_pages=ocr_pages,
                  empty_ocr_pages=empty_ocr_pages,
                  duration_ms=round((monotonic() - started) * 1000, 2))

        return ExtractedSource(
            source_type="pdf",
            units=units,
            metadata={"page_count": page_count, "ocr_pages": ocr_pages,
                      "empty_ocr_pages": empty_ocr_pages},
        )
