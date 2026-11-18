from pathlib import Path
from time import monotonic
from unittest.mock import Mock
import subprocess
import sys
import fitz
import pytest
from app.core.config import settings
from app.services.extraction.pdf_extraction_service import PdfExtractionService
from app.services.extraction.native_pdf_session import NativePDFSession
from app.services.extraction.ocr_session import OCRSession


def test_text_extraction_never_calls_parent_native_parser(tmp_path, monkeypatch):
    path=tmp_path/'native.pdf'
    with fitz.open() as pdf:
        pdf.new_page().insert_text((72,72),'Native text remains available')
        pdf.save(path)
    monkeypatch.setattr(fitz,'open',Mock(side_effect=AssertionError('Parent must not parse PDFs')))
    result=PdfExtractionService().extract(path)
    assert result.units[0].text=='Native text remains available'


def test_hung_native_parser_is_killed_and_reaped(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'pdf_native_page_timeout_seconds',.05)
    session=NativePDFSession(tmp_path/'input.pdf',settings,monotonic()+2)
    process=subprocess.Popen([sys.executable,'-c','import sys,time;sys.stdin.readline();time.sleep(60)'],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    session.process=process
    try:
        with pytest.raises(ValueError,match='timeout'):session.page_count(100)
    finally:session.close()
    assert process.poll() is not None and process.stdout.closed


@pytest.mark.parametrize('kind',[OCRSession,NativePDFSession])
def test_pdf_children_do_not_receive_application_credentials(kind,tmp_path,monkeypatch):
    for key in ['SECRET_KEY','DATABASE_URL','NVIDIA_API_KEY','GROQ_API_KEY','REDIS_URL']:
        monkeypatch.setenv(key,'do-not-forward-this-secret')
    process=Mock()
    monkeypatch.setattr(subprocess,'Popen',Mock(return_value=process))
    session=kind(tmp_path/'input.pdf',settings,monotonic()+2)
    session._start()
    env=subprocess.Popen.call_args.kwargs['env']
    assert not {'SECRET_KEY','DATABASE_URL','NVIDIA_API_KEY','GROQ_API_KEY','REDIS_URL'} & env.keys()
