"""Versioned OCR artifacts. Never download models on an upload request.

Digests are from RapidAI/RapidOCR v3.4.1 python/rapidocr/default_models.yaml.
"""

import hashlib
from pathlib import Path

MODEL_BASE_URL = "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.4.0/onnx"
DEFAULT_MODEL_DIR = Path(__file__).resolve().parents[3] / "models/ocr"
MODELS = {
    "det": ("PP-OCRv4/det/ch_PP-OCRv4_det_infer.onnx",
            "d2a7720d45a54257208b1e13e36a8479894cb74155a5efe29462512d42f49da9"),
    "cls": ("PP-OCRv4/cls/ch_ppocr_mobile_v2.0_cls_infer.onnx",
            "e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c"),
    "rec": ("PP-OCRv5/rec/latin_PP-OCRv5_rec_mobile_infer.onnx",
            "b20bd37c168a570f583afbc8cd7925603890efbcdc000a59e22c269d160b5f5a"),
}


def verify_model(path: Path, expected: str) -> None:
    if not path.is_file():
        raise ValueError("OCR models unavailable. Run python -m app.commands.prepare_ocr_models before starting workers.")
    with path.open("rb") as model:
        actual = hashlib.file_digest(model, "sha256").hexdigest()
    if actual != expected:
        raise ValueError("OCR model checksum mismatch. Reinstall the pinned OCR models.")


def verified_models(directory: Path) -> dict[str, Path]:
    paths = {}
    for role, (relative, digest) in MODELS.items():
        path = directory / Path(relative).name
        verify_model(path, digest)
        paths[role] = path
    return paths
