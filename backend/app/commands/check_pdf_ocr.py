"""Offline real-model smoke test: Vietnamese, English, mixed PDF, page citations.

Requires provisioned models and normal app settings. Never calls AI providers.
"""

from pathlib import Path
import tempfile
from time import monotonic
import unicodedata

import fitz

from app.services.chunk_service import ChunkingService
from app.services.extraction.pdf_extraction_service import PdfExtractionService


def normalize_ocr_text(text: str) -> str:
    # OCR boxes may split a phrase across lines. Whitespace is not a recognition
    # error; accents and letters still have to match exactly.
    return " ".join(unicodedata.normalize("NFC", text).lower().split())


def check_ocr():
    started = monotonic()
    with tempfile.TemporaryDirectory(prefix="askmemind-ocr-") as directory:
        path = Path(directory) / "scan.pdf"
        with fitz.open() as document:
            document.new_page().insert_text((40, 60), "Native text stays unchanged.")
            for text in (
                "Scanned document. Payment contract. Invoice number 2026.",
                "Tài liệu tiếng Việt. Hợp đồng thanh toán. Hóa đơn năm 2026.",
            ):
                with fitz.open() as original:
                    page = original.new_page(width=595, height=842)
                    page.insert_htmlbox(fitz.Rect(40, 40, 555, 250),
                                        f'<p style="font-size:24pt">{text}</p>')
                    pixels = page.get_pixmap(dpi=180)
                    scan = document.new_page(width=595, height=842)
                    scan.insert_image(scan.rect, pixmap=pixels)
                    assert not scan.get_text().strip(), "Smoke fixture must be image-only"
            document.new_page()  # Blank pages must not trigger OCR.
            document.save(path)
        source = PdfExtractionService().extract(path)
        assert [unit.page_number for unit in source.units] == [1, 2, 3]
        assert source.units[0].text == "Native text stays unchanged."
        assert source.metadata["ocr_pages"] == 2
        for unit, keywords in zip(source.units[1:], (
            ("scanned document", "payment contract", "2026"),
            ("tiếng việt", "hợp đồng", "thanh toán"),
        )):
            text = normalize_ocr_text(unit.text)
            hits = sum(keyword in text for keyword in keywords)
            # Only this command's synthetic fixture is printed on failure, never
            # text from user-uploaded PDFs in the ingestion pipeline.
            assert hits >= 2, (
                f"OCR quality check failed on page {unit.page_number}: {hits}/3 keywords; "
                f"missing={[keyword for keyword in keywords if keyword not in text]!r}; "
                f"synthetic_ocr_text={unit.text!r}"
            )
        chunks = ChunkingService().chunk_source(source)
        assert {chunk.page_number for chunk in chunks} == {1, 2, 3}
    print(f"Real OCR smoke passed: English, Vietnamese, mixed PDF and page metadata ({monotonic() - started:.2f}s).")


if __name__ == "__main__":
    check_ocr()
