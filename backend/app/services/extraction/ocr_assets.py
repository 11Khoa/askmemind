"""Versioned OCR artifacts. Never download models on an upload request.

Detector/classifier digests are from RapidAI/RapidOCR v3.4.1. Recognition
digests are the published GitHub ocr-v1 release asset digests of
duchoa1297/vietocr-onnx (Apache-2.0 exports of pbcquoc/vietocr).
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
    "encoder": ("https://github.com/duchoa1297/vietocr-onnx/releases/download/ocr-v1/vietocr_encoder.onnx",
                "7375c11ad23d52547a344ec5f53adf89db8302f035ceb3f1e67cff2c04069ae7"),
    "decoder": ("https://github.com/duchoa1297/vietocr-onnx/releases/download/ocr-v1/vietocr_decoder.onnx",
                "73b92cd370563952b345703ecdce84d8374a9f0a7018afee062170efe04f21f5"),
    "vocab": ("https://github.com/duchoa1297/vietocr-onnx/releases/download/ocr-v1/vietocr.json",
              "518345b7672fd36e534fb8ffcf6f6599c687793541259170834789fe2f7dd6e6"),
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
