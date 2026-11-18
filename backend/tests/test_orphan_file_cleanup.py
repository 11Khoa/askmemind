import os
import uuid
from unittest.mock import Mock

from app.services.orphan_file_cleanup import cleanup_orphan_uploads


def test_sweep_keeps_references_recent_unknown_and_symlink_files(tmp_path):
    old = tmp_path / f'{uuid.uuid4()}.pdf'
    referenced = tmp_path / f'{uuid.uuid4()}.pdf'
    recent = tmp_path / f'{uuid.uuid4()}.pdf'
    unrelated = tmp_path / 'manual.pdf'
    temporary = tmp_path / '.upload-test.part'
    for path in (old, referenced, recent, unrelated, temporary):
        path.write_bytes(b'pdf')
        os.utime(path, (1, 1))
    os.utime(recent, (100000, 100000))
    link = tmp_path / f'{uuid.uuid4()}.pdf'
    link.symlink_to(unrelated)
    db = Mock()
    db.scalar.side_effect = lambda query: uuid.uuid4() if referenced.name in query.compile().params.values() else None
    assert cleanup_orphan_uploads(db, str(tmp_path), now=100000) == 2
    assert not old.exists() and not temporary.exists()
    assert all(path.exists() for path in (referenced, recent, unrelated, link))
    assert cleanup_orphan_uploads(db, str(tmp_path), now=100000) == 0
