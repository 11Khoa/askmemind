from pathlib import Path


class FileStorageService:
    def __init__(self, upload_dir: str):
        self.upload_dir = Path(upload_dir)

    def save_upload(self, file_bytes: bytes, filename: str) -> str:
        if "/" in filename or "\\" in filename or ".." in filename:
            raise ValueError("Invalid filename")

        self.upload_dir.mkdir(parents=True, exist_ok=True)

        file_path = self.upload_dir / filename

        file_path.write_bytes(file_bytes)

        return str(file_path)

    def delete_file(self, file_path: str) -> None:
        path = Path(file_path)

        if path.exists():
            path.unlink()
