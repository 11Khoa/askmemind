from pathlib import Path

import pytest

from app.services.file_storage_service import FileStorageService


def test_save_upload_writes_file_bytes(tmp_path: Path) -> None:
    upload_dir = tmp_path / "uploads"
    service = FileStorageService(upload_dir=str(upload_dir))

    result = service.save_upload(
        file_bytes=b"fake pdf content",
        filename="test.pdf",
    )

    save_path = Path(result)

    assert save_path.exists()
    assert save_path.read_bytes() == b"fake pdf content"
    assert save_path.name == "test.pdf"
    assert save_path.parent == upload_dir


def test_save_upload_creates_upload_directory(tmp_path: Path) -> None:
    upload_dir = tmp_path / "uploads"
    service = FileStorageService(upload_dir=str(upload_dir))

    assert not upload_dir.exists()

    service.save_upload(
        file_bytes=b"content",
        filename="test.pdf",
    )

    assert upload_dir.exists()
    assert upload_dir.is_dir()


def test_save_upload_rejects_filename_with_forward_slash(tmp_path: Path) -> None:
    service = FileStorageService(upload_dir=str(tmp_path))

    with pytest.raises(ValueError, match="Invalid filename"):
        service.save_upload(
            file_bytes=b"content",
            filename="folder/test.pdf",
        )


def test_save_upload_rejects_filename_with_parent_directory(tmp_path: Path) -> None:
    service = FileStorageService(upload_dir=str(tmp_path))

    with pytest.raises(ValueError, match="Invalid filename"):
        service.save_upload(
            file_bytes=b"content",
            filename="../test.pdf",
        )


def test_save_upload_rejects_filename_with_backslash(tmp_path: Path) -> None:
    service = FileStorageService(upload_dir=str(tmp_path))

    with pytest.raises(ValueError, match="Invalid filename"):
        service.save_upload(
            file_bytes=b"content",
            filename="test\\.pdf",
        )


def test_delete_file_removes_existing_file(tmp_path: Path) -> None:
    file_path = tmp_path / "test.pdf"
    file_path.write_bytes(b"content")

    service = FileStorageService(upload_dir=str(tmp_path))

    service.delete_file(file_path=str(file_path))

    assert not file_path.exists()


def test_delete_file_ignores_missing_file(tmp_path: Path) -> None:
    file_path = tmp_path / "missing.pdf"

    service = FileStorageService(upload_dir=str(tmp_path))

    service.delete_file(file_path=str(file_path))

    assert not file_path.exists()
