import hashlib
import json
import multiprocessing
from pathlib import Path
import subprocess
import sys
from time import monotonic
from types import SimpleNamespace
from unittest.mock import Mock

import fitz
import numpy as np
import pytest

from app.core.config import settings
from app.services.extraction import pdf_extraction_service as extraction
from app.services.extraction.ocr_assets import verify_model
from app.services.extraction.ocr_session import OCRSession
from app.services.extraction.ocr_worker import recognize_page
from app.services.chunk_service import ChunkingService


def make_pdf(path, native=False, scans=1, header=False):
    with fitz.open() as document:
        if native:
            document.new_page().insert_text((72, 72), "Native text is preserved")
        for _ in range(scans):
            page = document.new_page(width=300, height=400)
            pixels = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 200, 200), False)
            pixels.clear_with(255)
            page.insert_image(page.rect, pixmap=pixels)
            if header:
                page.insert_text((10, 20), "Short header")
        document.save(path)
    return path


@pytest.fixture
def fake_session(monkeypatch):
    session = Mock()
    session.recognize.return_value = {"text": "Tài liệu tiếng Việt\nScanned document", "confidence": 0.98}
    monkeypatch.setattr(extraction, "OCRSession", Mock(return_value=session))
    monkeypatch.setattr(settings, "pdf_ocr_enabled", True)
    return session


def test_mixed_pdf_ocr_preserves_pages_and_chunk_metadata(tmp_path, fake_session):
    source = extraction.PdfExtractionService().extract(make_pdf(tmp_path / "mixed.pdf", native=True))
    assert [unit.page_number for unit in source.units] == [1, 2]
    assert source.units[0].text == "Native text is preserved"
    assert source.units[1].text.startswith("Tài liệu tiếng Việt")
    assert source.metadata["ocr_pages"] == 1
    fake_session.recognize.assert_called_once()
    assert fake_session.recognize.call_args.args[0] == 1
    chunks = ChunkingService().chunk_source(source)
    assert chunks[1].page_number == 2
    assert chunks[1].metadata["extraction_method"] == "ocr"
    fake_session.close.assert_called_once()


def test_native_and_blank_pages_do_not_invoke_ocr(tmp_path, fake_session):
    path = tmp_path / "native.pdf"
    with fitz.open() as document:
        document.new_page().insert_text((72, 72), "Hello")
        document.new_page()
        document.save(path)
    result = extraction.PdfExtractionService().extract(path)
    assert result.units[0].text == "Hello"
    fake_session.recognize.assert_not_called()


def test_short_header_over_scan_is_not_mistaken_for_text_pdf(tmp_path, fake_session):
    result = extraction.PdfExtractionService().extract(make_pdf(tmp_path / "header.pdf", header=True))
    assert result.units[0].text == fake_session.recognize.return_value["text"]
    assert "Short header" not in result.units[0].text


def test_disabled_ocr_does_not_start_worker(tmp_path, fake_session, monkeypatch):
    monkeypatch.setattr(settings, "pdf_ocr_enabled", False)
    with pytest.raises(ValueError, match="does not contain extractable text"):
        extraction.PdfExtractionService().extract(make_pdf(tmp_path / "scan.pdf"))
    fake_session.recognize.assert_not_called()


def test_ocr_page_limit_fails_instead_of_silently_truncating(tmp_path, fake_session, monkeypatch):
    monkeypatch.setattr(settings, "pdf_ocr_max_pages", 1)
    with pytest.raises(ValueError, match="OCR page limit"):
        extraction.PdfExtractionService().extract(make_pdf(tmp_path / "large.pdf", scans=2))
    assert fake_session.recognize.call_count == 1
    fake_session.close.assert_called_once()


def test_ocr_text_counts_towards_existing_character_limit(tmp_path, fake_session):
    with pytest.raises(ValueError, match="extracted text limit"):
        extraction.PdfExtractionService(max_text_characters=5).extract(make_pdf(tmp_path / "scan.pdf"))
    fake_session.close.assert_called_once()


def test_ocr_failure_does_not_produce_partial_success(tmp_path, fake_session):
    fake_session.recognize.side_effect = ValueError("OCR timeout")
    with pytest.raises(ValueError, match="OCR timeout"):
        extraction.PdfExtractionService().extract(make_pdf(tmp_path / "scan.pdf", native=True))
    fake_session.close.assert_called_once()


def test_no_confident_text_keeps_native_header_and_reports_empty_page(tmp_path, fake_session):
    fake_session.recognize.return_value = {"text": "", "confidence": None}
    source = extraction.PdfExtractionService().extract(make_pdf(tmp_path / "scan.pdf", header=True))
    assert source.units[0].text == "Short header"
    assert source.metadata["empty_ocr_pages"] == [1]
    assert "extraction_method" not in source.units[0].metadata


def test_page_render_is_bounded_and_confidence_filter_handles_numpy(tmp_path):
    path = make_pdf(tmp_path / "render.pdf")
    engine = Mock(return_value=SimpleNamespace(
        txts=("Reliable text", "noise", "invalid"), scores=np.array([0.95, 0.1, np.nan]),
    ))
    result = recognize_page(engine, {"file_path": str(path), "dpi": 300,
                            "max_pixels": 100_000, "min_confidence": 0.6},
                            {"page_index": 0, "max_characters": 100})
    image = engine.call_args.args[0]
    assert image.shape[0] * image.shape[1] <= 100_000
    assert image.shape[2] == 3
    assert result == {"text": "Reliable text", "confidence": 0.95}


def test_worker_rejects_excessive_ocr_output(tmp_path):
    path = make_pdf(tmp_path / "render.pdf")
    engine = Mock(return_value=SimpleNamespace(txts=("too long",), scores=(0.99,)))
    with pytest.raises(ValueError, match="extracted text limit"):
        recognize_page(engine, {"file_path": str(path), "dpi": 72,
                       "max_pixels": 100_000, "min_confidence": 0.6},
                       {"page_index": 0, "max_characters": 3})


def test_ocr_text_at_exact_limit_is_accepted(tmp_path):
    engine = Mock(return_value=SimpleNamespace(txts=("exact",), scores=(0.99,)))
    result = recognize_page(engine, {"file_path": str(make_pdf(tmp_path / "boundary.pdf")),
                            "dpi": 72, "max_pixels": 100_000, "min_confidence": 0.6},
                            {"page_index": 0, "max_characters": 5})
    assert result["text"] == "exact"


def test_extremely_thin_page_is_bounded_before_render(tmp_path):
    path = tmp_path / "thin.pdf"
    with fitz.open() as document:
        document.new_page(width=1_000_000, height=1)
        document.save(path)
    engine = Mock(return_value=SimpleNamespace(txts=None, scores=None))
    recognize_page(engine, {"file_path": str(path), "dpi": 300,
                   "max_pixels": 100_000, "min_confidence": 0.6},
                   {"page_index": 0, "max_characters": 5})
    image = engine.call_args.args[0]
    assert max(image.shape[:2]) <= 4096
    assert image.shape[0] * image.shape[1] <= 100_000


def test_model_checksum_rejects_missing_and_corrupt_files(tmp_path):
    path = tmp_path / "model.onnx"
    digest = hashlib.sha256(b"expected").hexdigest()
    with pytest.raises(ValueError, match="models unavailable"):
        verify_model(path, digest)
    path.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="checksum mismatch"):
        verify_model(path, digest)
    path.write_bytes(b"expected")
    verify_model(path, digest)


def session_with_child(tmp_path, monkeypatch, program):
    session = OCRSession(tmp_path / "input.pdf", settings, monotonic() + 5)
    process = subprocess.Popen([sys.executable, "-u", "-c", program],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    session.process = process
    # Short test deadlines without invalid production settings.
    session.config = SimpleNamespace(pdf_ocr_page_timeout_seconds=0.15)
    return session, process


def test_timeout_kills_and_reaps_native_subprocess(tmp_path, monkeypatch):
    session, process = session_with_child(tmp_path, monkeypatch,
        "import sys,time; sys.stdin.readline(); time.sleep(10)")
    try:
        with pytest.raises(ValueError, match="timeout"):
            session.recognize(0, 100)
    finally:
        session.close()
    assert process.returncode is not None
    assert process.stdout.closed and process.stdin.closed


def test_subprocess_crash_becomes_actionable_error(tmp_path, monkeypatch):
    session, process = session_with_child(tmp_path, monkeypatch, "import sys; sys.stdin.readline()")
    try:
        with pytest.raises(ValueError, match="exited unexpectedly"):
            session.recognize(0, 100)
    finally:
        session.close()
    assert process.returncode is not None


def test_subprocess_protocol_supports_multiple_pages(tmp_path, monkeypatch):
    response = json.dumps({"text": "Tiếng Việt", "confidence": 0.99})
    session, _ = session_with_child(tmp_path, monkeypatch,
        f"import sys\nfor line in sys.stdin:\n print({response!r},flush=True)")
    try:
        assert session.recognize(0, 100)["text"] == "Tiếng Việt"
        assert session.recognize(1, 100)["text"] == "Tiếng Việt"
    finally:
        session.close()


@pytest.mark.parametrize("response", ["not-json", "[]", '{"text": "hello"}',
                                    '{"text": "long text", "confidence": 0.9}'])
def test_invalid_or_oversized_responses_fail_safely(tmp_path, monkeypatch, response):
    session, _ = session_with_child(tmp_path, monkeypatch,
        f"import sys; sys.stdin.readline(); print({response!r},flush=True)")
    try:
        with pytest.raises(ValueError, match="OCR worker response"):
            session.recognize(0, 3)
    finally:
        session.close()


def test_document_deadline_prevents_starting_more_work(tmp_path):
    session = OCRSession(tmp_path / "input.pdf", settings, monotonic() - 1)
    with pytest.raises(ValueError, match="document timeout"):
        session.recognize(0, 100)
    assert session.process is None


def _daemon_extract(path, connection):
    try:
        extraction.PdfExtractionService().extract(Path(path))
    except ValueError as error:
        connection.send(str(error))
    finally:
        connection.close()


@pytest.mark.skipif(sys.platform != "linux", reason="Celery prefork production target is Linux")
def test_ocr_subprocess_can_run_inside_daemon_worker(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "pdf_ocr_model_dir", tmp_path / "missing-models")
    path = make_pdf(tmp_path / "scan.pdf")
    context = multiprocessing.get_context("fork")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(target=_daemon_extract, args=(str(path), child), daemon=True)
    process.start()
    child.close()
    try:
        assert parent.poll(10), "OCR subprocess stalled inside a daemon worker"
        assert "models unavailable" in parent.recv()
        process.join(3)
        assert process.exitcode == 0
    finally:
        if process.is_alive():
            process.kill()
            process.join()
        parent.close()


def test_missing_models_reported_by_real_worker_without_network(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "pdf_ocr_model_dir", tmp_path / "missing-models")
    with pytest.raises(ValueError, match="models unavailable"):
        extraction.PdfExtractionService().extract(make_pdf(tmp_path / "scan.pdf"))


@pytest.mark.parametrize("field,value", [
    ("pdf_ocr_dpi", 0), ("pdf_ocr_max_pixels", 0),
    ("pdf_ocr_max_pages", 0), ("pdf_ocr_page_timeout_seconds", 0),
    ("pdf_ocr_document_timeout_seconds", 0), ("pdf_ocr_min_confidence", 1.1),
    ("pdf_ocr_threads", 0),
])
def test_unsafe_ocr_settings_fail_validation(field, value):
    from app.core.config import Settings
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url="sqlite://", secret_key="test", **{field: value})
