"""Bounded, lazy OCR subprocess with deterministic cleanup on every exit path."""

import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
from time import monotonic

from app.core.config import Settings


class OCRSession:
    def __init__(self, file_path: Path, config: Settings, deadline: float):
        self.file_path = file_path
        self.config = config
        self.deadline = deadline
        self.process = None
        self.ensure_active = None

    def _start(self):
        config = self.config
        environment = os.environ.copy()
        for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
            environment[name] = str(config.pdf_ocr_threads)
        self.process = subprocess.Popen(
            [sys.executable, "-m", "app.services.extraction.ocr_worker"],
            cwd=Path(__file__).resolve().parents[3], env=environment,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        self._send({
            "file_path": str(self.file_path.resolve()),
            "model_dir": str(config.pdf_ocr_model_dir.resolve()),
            "dpi": config.pdf_ocr_dpi, "max_pixels": config.pdf_ocr_max_pixels,
            "min_confidence": config.pdf_ocr_min_confidence,
            "threads": config.pdf_ocr_threads,
        })

    def _send(self, message):
        try:
            self.process.stdin.write((json.dumps(message) + "\n").encode())
            self.process.stdin.flush()
        except (BrokenPipeError, OSError) as error:
            raise ValueError("OCR worker exited unexpectedly. Check OCR installation and retry.") from error

    def recognize(self, page_index: int, max_characters: int) -> dict:
        if self.ensure_active is not None:
            self.ensure_active()
        deadline = min(self.deadline, monotonic() + self.config.pdf_ocr_page_timeout_seconds)
        if monotonic() >= deadline:
            raise ValueError("PDF OCR exceeded the configured document timeout")
        if self.process is None:
            self._start()
        self._send({"page_index": page_index, "max_characters": max_characters})
        # JSON ASCII escaping can use six bytes per character.
        max_bytes = max_characters * 6 + 4096
        output = bytearray()
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdout, selectors.EVENT_READ)
            while True:
                remaining = deadline - monotonic()
                if self.ensure_active is not None:
                    self.ensure_active()
                if remaining <= 0:
                    raise ValueError("PDF OCR exceeded the configured page or document timeout")
                if not selector.select(min(1.0, remaining) if self.ensure_active is not None else remaining):
                    if self.ensure_active is not None:
                        continue
                    raise ValueError("PDF OCR exceeded the configured page or document timeout")
                block = os.read(self.process.stdout.fileno(), min(65536, max_bytes + 1 - len(output)))
                if not block:
                    raise ValueError("OCR worker exited unexpectedly. Check OCR installation and retry.")
                output.extend(block)
                if len(output) > max_bytes:
                    raise ValueError("PDF exceeds the configured extracted text limit")
                if b"\n" in output:
                    break
        try:
            result = json.loads(output)
        except (ValueError, UnicodeError) as error:
            raise ValueError("Invalid OCR worker response") from error
        if not isinstance(result, dict):
            raise ValueError("Invalid OCR worker response")
        if "error" in result:
            raise ValueError(result["error"])
        if (not isinstance(result.get("text"), str)
                or len(result["text"]) > max_characters
                or "confidence" not in result):
            raise ValueError("Invalid or oversized OCR worker response")
        return result

    def close(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.kill()
            self.process.wait()
            self.process.stdin.close()
            self.process.stdout.close()
