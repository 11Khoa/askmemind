"""All native PDF parsing lives in a disposable bounded interpreter."""
import os
from pathlib import Path
import subprocess
import sys
from app.services.extraction.ocr_session import OCRSession


class NativePDFSession(OCRSession):
    def _start(self):
        environment = {name: os.environ[name] for name in (
            "PATH", "LANG", "LC_ALL", "PYTHONPATH", "LD_LIBRARY_PATH", "SYSTEMROOT", "TMPDIR",
        ) if name in os.environ}
        for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
            environment[name] = "1"
        self.process = subprocess.Popen(
            [sys.executable, "-m", "app.services.extraction.native_pdf_worker"],
            cwd=Path(__file__).resolve().parents[3], env=environment,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        self._send({"file_path": str(self.file_path.resolve()),
                    "memory_mb": self.config.pdf_native_memory_mb,
                    "cpu_seconds": self.config.pdf_ocr_document_timeout_seconds})

    def page_count(self, max_pages):
        result = self._exchange({"action": "info"}, 4096, self.config.pdf_native_page_timeout_seconds)
        count = result.get("page_count")
        if type(count) is not int or count < 1:
            raise ValueError("Invalid PDF page count")
        if count > max_pages:
            raise ValueError("PDF exceeds the configured page limit")
        return count

    def page(self, index, max_characters):
        result = self._exchange({"action": "page", "page_index": index, "max_characters": max_characters},
                                max_characters * 6 + 4096, self.config.pdf_native_page_timeout_seconds)
        if not isinstance(result.get("text"), str) or len(result["text"]) > max_characters or type(result.get("needs_ocr")) is not bool:
            raise ValueError("Invalid or oversized PDF worker response")
        return result
