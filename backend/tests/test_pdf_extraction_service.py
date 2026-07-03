from pathlib import Path

import pytest
import fitz

from app.services.extraction.pdf_extraction_service import PdfExtractionService


def test_extract_returns_text_units_with_pdf_page_numbers(tmp_path: Path) -> None:
    pdf_path = tmp_path / "test.pdf"

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Hello Test")
    document.save(pdf_path)
    document.close()

    service = PdfExtractionService()

    result = service.extract(pdf_path)

    assert result.source_type == "pdf"
    assert result.metadata["page_count"] == 1
    assert len(result.units) == 1
    assert result.units[0].text == "Hello Test"
    assert result.units[0].page_number == 1


def test_extract_returns_text_units_with_one_based_page_numbers(tmp_path: Path) -> None:
    pdf_path = tmp_path / "test.pdf"

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Hello Test")
    page = document.new_page()
    page.insert_text((72, 72), "Hello Test Page2")
    document.save(pdf_path)
    document.close()

    service = PdfExtractionService()

    result = service.extract(pdf_path)

    assert result.source_type == "pdf"
    assert result.metadata["page_count"] == 2
    assert len(result.units) == 2

    assert result.units[0].text == "Hello Test"
    assert result.units[0].page_number == 1

    assert result.units[1].text == "Hello Test Page2"
    assert result.units[1].page_number == 2


def test_extract_raises_error_when_pdf_has_no_text(tmp_path: Path) -> None:
    pdf_path = tmp_path / "test.pdf"

    document = fitz.open()
    document.new_page()
    document.save(pdf_path)
    document.close()

    service = PdfExtractionService()

    with pytest.raises(ValueError, match="PDF does not contain extractable text"):
        service.extract(pdf_path)
