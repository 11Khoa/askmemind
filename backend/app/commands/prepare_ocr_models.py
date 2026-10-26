"""Provision and verify pinned models at build/deploy time, not at ingestion time."""

import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import tempfile
import urllib.request

from app.services.extraction.ocr_assets import (
    DEFAULT_MODEL_DIR, MODELS, MODEL_BASE_URL, verify_model,
)


def prepare_models(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.find_spec("rapidocr")
    bundled = Path(spec.origin).parent / "models" if spec and spec.origin else None
    for relative, digest in MODELS.values():
        target = directory / Path(relative).name
        if target.exists():
            verify_model(target, digest)
            continue
        fd, temporary = tempfile.mkstemp(dir=directory, suffix=".part")
        try:
            with os.fdopen(fd, "wb") as output:
                source = bundled / target.name if bundled else None
                if source and source.is_file():
                    with source.open("rb") as model:
                        shutil.copyfileobj(model, output)
                else:
                    url = relative if relative.startswith("https://") else f"{MODEL_BASE_URL}/{relative}"
                    with urllib.request.urlopen(url, timeout=60) as response:
                        shutil.copyfileobj(response, output)
            verify_model(Path(temporary), digest)
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)
    print("Pinned OCR models verified.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(os.environ.get("PDF_OCR_MODEL_DIR", DEFAULT_MODEL_DIR)))
    prepare_models(parser.parse_args().output)
