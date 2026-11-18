"""Remove abandoned uploads conservatively, retaining every database reference."""
import logging
import time
import uuid
from pathlib import Path

from sqlalchemy import select

from app.models.document import Document

logger = logging.getLogger(__name__)


def cleanup_orphan_uploads(db, upload_dir: str, *, now=None, limit=500) -> int:
    directory = Path(upload_dir)
    if not directory.is_dir():
        return 0
    cutoff = (time.time() if now is None else now) - 86400
    removed = 0
    for path in directory.iterdir():
        if removed >= limit:
            break
        if path.is_symlink() or not path.is_file():
            continue
        temporary = path.name.startswith('.upload-') and path.suffix == '.part'
        try:
            generated_pdf = path.suffix == '.pdf' and str(uuid.UUID(path.stem)) == path.stem
        except ValueError:
            generated_pdf = False
        if not temporary and not generated_pdf:
            continue
        try:
            if path.stat().st_mtime >= cutoff:
                continue
            # Match the stored filename regardless of deployment's absolute path.
            if db.scalar(select(Document.id).where(Document.filename == path.name).limit(1)) is not None:
                continue
            path.unlink(missing_ok=True)
            removed += 1
        except OSError:
            logger.warning('storage.orphan_cleanup_retry')
    if removed:
        logger.info('storage.orphans_removed', extra={'removed_count': removed})
    return removed
