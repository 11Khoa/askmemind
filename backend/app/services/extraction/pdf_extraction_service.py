from pathlib import Path
import logging
import hashlib
import json
from time import monotonic

import fitz

from app.core.config import settings
from app.core.logging import log_event
from app.services.extraction.ocr_session import OCRSession
from app.services.extraction.ocr_assets import MODELS
from app.services.extraction.base import ExtractionCheckpoint

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

    def extract(self, file_path: Path, *, checkpoint: ExtractionCheckpoint | None = None) -> ExtractedSource:
        started = monotonic()
        session = OCRSession(file_path, settings, started + settings.pdf_ocr_document_timeout_seconds)
        if checkpoint is not None and hasattr(checkpoint, "ensure_active"):
            session.ensure_active = checkpoint.ensure_active
        try:
            return self._extract(file_path, session, started, checkpoint)
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

    def _fingerprint(self, file_path: Path) -> str:
        with file_path.open("rb") as pdf:
            file_hash = hashlib.file_digest(pdf, "sha256").hexdigest()
        configuration = {
            "version": 1, "file": file_hash, "models": MODELS,
            "enabled": settings.pdf_ocr_enabled, "dpi": settings.pdf_ocr_dpi,
            "pixels": settings.pdf_ocr_max_pixels, "confidence": settings.pdf_ocr_min_confidence,
        }
        return hashlib.sha256(json.dumps(configuration, sort_keys=True).encode()).hexdigest()

    def _extract(self, file_path: Path, session: OCRSession, started: float,
                 checkpoint: ExtractionCheckpoint | None = None) -> ExtractedSource:
        units: list[ExtractedTextUnit] = []
        text_characters = 0
        ocr_pages = 0
        empty_ocr_pages = []
        reused_pages = 0
        with fitz.open(file_path) as document:
            page_count = document.page_count
            if page_count > self.max_pages:
                raise ValueError("PDF exceeds the configured page limit")
            cached = checkpoint.begin(self._fingerprint(file_path), page_count) if checkpoint else {}

            for page_index in range(page_count):
                number = page_index + 1
                entry = cached.get(number)
                if entry is not None:
                    reused_pages += 1
                    text = entry["text"]
                    stored = entry["metadata"]
                    metadata = {k: v for k, v in stored.items() if not k.startswith("_")}
                    needs_ocr = stored.get("_ocr_attempted", False)
                    empty_ocr = stored.get("_ocr_empty", False)
                else:
                    page = document.load_page(page_index)
                    text = page.get_text().strip()
                    metadata = {}
                    needs_ocr = settings.pdf_ocr_enabled and self._needs_ocr(page, text)
                    empty_ocr = False
                if checkpoint:
                    checkpoint.report(stage="ocr" if needs_ocr and entry is None else "extracting",
                                      current_page=number, completed_pages=page_index,
                                      total_pages=page_count, reused_pages=reused_pages)
                if needs_ocr:
                    ocr_pages += 1
                    if ocr_pages > settings.pdf_ocr_max_pages:
                        raise ValueError("PDF exceeds the configured OCR page limit. Split the PDF and retry.")
                if needs_ocr and entry is None:
                    try:
                        result = session.recognize(page_index, self.max_text_characters - text_characters)
                    except Exception:
                        logger.error("pdf.ocr.page.failed page=%s total=%s", number, page_count)
                        raise
                    # Prefer a complete OCR rendering over a partial text header.
                    # If OCR finds no reliable text, keep any existing native text.
                    if result["text"].strip():
                        text = result["text"].strip()
                        metadata = {"extraction_method": "ocr", "ocr_confidence": result["confidence"]}
                    else:
                        empty_ocr = True
                if empty_ocr:
                    empty_ocr_pages.append(number)
                text_characters += len(text)
                if text_characters > self.max_text_characters:
                    raise ValueError("PDF exceeds the configured extracted text limit")
                if checkpoint:
                    if entry is None:
                        checkpoint.save(number, text, {**metadata, "_ocr_attempted": bool(needs_ocr),
                                                       "_ocr_empty": empty_ocr})
                    checkpoint.report(completed_pages=number, reused_pages=reused_pages)

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
                      "empty_ocr_pages": empty_ocr_pages, "reused_pages": reused_pages},
        )
