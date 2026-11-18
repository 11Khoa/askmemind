import os
import tempfile
from pathlib import Path


class FileStorageService:
    def __init__(self, upload_dir: str):
        self.upload_dir = Path(upload_dir)

    def save_upload(self, file_bytes: bytes, filename: str) -> str:
        if "/" in filename or "\\" in filename or ".." in filename:
            raise ValueError("Invalid filename")

        self.upload_dir.mkdir(parents=True, exist_ok=True)

        file_path = self.upload_dir / filename

        # Publish only a fully flushed file; failures leave no partial PDF.
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=self.upload_dir, prefix=".upload-", suffix=".part", delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(file_bytes)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, file_path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

        return str(file_path)

    def delete_file(self, file_path: str) -> None:
        path = Path(file_path)

        if path.exists():
            path.unlink()
