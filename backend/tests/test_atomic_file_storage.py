from unittest.mock import patch

import pytest

from app.services.file_storage_service import FileStorageService


def test_write_failure_keeps_existing_pdf_and_removes_partial_file(tmp_path):
    target = tmp_path / 'document.pdf'
    target.write_bytes(b'existing')
    with patch('app.services.file_storage_service.os.fsync', side_effect=OSError('disk full')):
        with pytest.raises(OSError):
            FileStorageService(str(tmp_path)).save_upload(b'incomplete', 'document.pdf')
    assert target.read_bytes() == b'existing'
    assert list(tmp_path.iterdir()) == [target]


def test_success_publishes_complete_pdf_without_temporary_file(tmp_path):
    target = FileStorageService(str(tmp_path)).save_upload(b'complete', 'document.pdf')
    assert (tmp_path / 'document.pdf').read_bytes() == b'complete'
    assert target == str(tmp_path / 'document.pdf')
    assert len(list(tmp_path.iterdir())) == 1
