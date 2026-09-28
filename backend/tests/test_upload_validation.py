from io import BytesIO
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from app.routers.upload import _read_validated_pdf


def _upload(content: bytes, content_type: str = "application/pdf") -> Mock:
    upload = Mock()
    upload.content_type = content_type
    upload.file = BytesIO(content)
    return upload


def test_read_validated_pdf_accepts_pdf_within_limit() -> None:
    content = b"%PDF-1.7\nvalid"

    assert _read_validated_pdf(
        file=_upload(content),
        max_size_bytes=len(content),
    ) == content


def test_read_validated_pdf_rejects_oversized_upload() -> None:
    with pytest.raises(HTTPException) as error:
        _read_validated_pdf(
            file=_upload(b"%PDF-1.7\ntoo large"),
            max_size_bytes=8,
        )

    assert error.value.status_code == 413


@pytest.mark.parametrize(
    ("content", "content_type", "detail"),
    [
        (b"", "application/pdf", "Uploaded PDF is empty"),
        (
            b"not a pdf",
            "application/pdf",
            "Uploaded file does not have a valid PDF header",
        ),
        (
            b"%PDF-1.7",
            "text/plain",
            "Only PDF uploads are supported",
        ),
    ],
)
def test_read_validated_pdf_rejects_invalid_uploads(
    content: bytes,
    content_type: str,
    detail: str,
) -> None:
    with pytest.raises(HTTPException) as error:
        _read_validated_pdf(
            file=_upload(content, content_type),
            max_size_bytes=1024,
        )

    assert error.value.status_code == 400
    assert error.value.detail == detail
