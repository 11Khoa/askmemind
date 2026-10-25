"""Private subprocess protocol; stdout is reserved for JSON, never document logs.

A separate interpreter works inside Celery prefork (daemon) workers and can be
killed even while native ONNX inference is running. One engine per document.
"""

import contextlib
import json
import math
import os
from pathlib import Path
import sys

from app.services.extraction.ocr_assets import verified_models


def exit_if_parent_dies():
    """Do not leave native inference orphaned after a Linux Celery worker dies."""
    if sys.platform == "linux":
        import ctypes
        import signal

        parent = os.getppid()
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0:  # PR_SET_PDEATHSIG
            raise OSError(ctypes.get_errno(), "Could not bind OCR worker lifetime to parent")
        if parent == 1 or os.getppid() != parent:
            os._exit(1)


def create_engine(options):
    paths = verified_models(Path(options["model_dir"]))
    import cv2
    import onnxruntime as ort
    from rapidocr import RapidOCR
    from rapidocr.utils.typings import LangRec, OCRVersion

    # RapidOCR constructs a visualizer even for text-only output. Supply the
    # Latin-capable font bundled with the pinned Linux OpenCV wheel so it does
    # not download a visualization font during inference.
    font_path = Path(cv2.__file__).parent / "qt/fonts/DejaVuSans.ttf"
    if not font_path.is_file():
        raise ValueError("OCR font unavailable. Install the pinned Linux opencv-python wheel.")
    cv2.setNumThreads(options["threads"])
    ort.disable_telemetry_events()
    session_options = ort.SessionOptions()
    session_options.intra_op_num_threads = options["threads"]
    session_options.inter_op_num_threads = 1
    session_options.enable_cpu_mem_arena = False
    recognition_session = ort.InferenceSession(
        str(paths["rec"]), sess_options=session_options,
        providers=["CPUExecutionProvider"],
    )
    # Reject incompatible recognizers instead of letting RapidOCR download a dict.
    if "character" not in recognition_session.get_modelmeta().custom_metadata_map:
        raise ValueError("OCR recognizer is missing its embedded character dictionary")
    del recognition_session
    # OmegaConf only accepts primitive configuration values. InferenceSession
    # objects in *.session fail before RapidOCR can initialize its engines.
    return RapidOCR(params={
        "Global.log_level": "critical",
        "Global.max_side_len": 4096,
        "Global.font_path": str(font_path),
        "Det.model_path": str(paths["det"]),
        "Cls.model_path": str(paths["cls"]),
        "Rec.model_path": str(paths["rec"]),
        "EngineConfig.onnxruntime.intra_op_num_threads": options["threads"],
        "EngineConfig.onnxruntime.inter_op_num_threads": 1,
        "EngineConfig.onnxruntime.enable_cpu_mem_arena": False,
        "EngineConfig.onnxruntime.use_cuda": False,
        "EngineConfig.onnxruntime.use_dml": False,
        "EngineConfig.onnxruntime.use_cann": False,
        "Rec.lang_type": LangRec.LATIN,
        "Rec.ocr_version": OCRVersion.PPOCRV5,
        "Rec.rec_batch_num": 1,
    })


def recognize_page(engine, options, request):
    import fitz
    import numpy as np

    with fitz.open(options["file_path"]) as document:
        page = document.load_page(request["page_index"])
        area = page.rect.width * page.rect.height
        if not math.isfinite(area) or area <= 0:
            raise ValueError("Invalid PDF page dimensions")
        scale = min(options["dpi"] / 72,
                    math.sqrt(options["max_pixels"] / area) * 0.99,
                    4096 / max(page.rect.width, page.rect.height))
        # Account for raster rounding before allocation, including very thin PDFs.
        while (max(1, math.ceil(page.rect.width * scale))
               * max(1, math.ceil(page.rect.height * scale)) > options["max_pixels"]):
            scale *= 0.9
        pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csRGB, alpha=False)
        if pixmap.width * pixmap.height > options["max_pixels"]:
            raise ValueError("OCR rendered page exceeds pixel limit")
        # RapidOCR's ndarray input uses OpenCV BGR ordering.
        image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width, 3)
        result = engine(image[:, :, ::-1].copy(), text_score=options["min_confidence"])
    lines = []
    size = 0
    scores = []
    texts = result.txts if result.txts is not None else ()
    confidences = result.scores if result.scores is not None else ()
    for text, score in zip(texts, confidences):
        if not math.isfinite(float(score)) or score < options["min_confidence"] or not text.strip():
            continue
        size += len(text.strip()) + (1 if lines else 0)
        if size > request["max_characters"]:
            raise ValueError("PDF exceeds the configured extracted text limit")
        lines.append(text.strip())
        scores.append(float(score))
    return {"text": "\n".join(lines), "confidence": sum(scores) / len(scores) if scores else None}


def main():
    exit_if_parent_dies()
    wire = sys.stdout
    # Third party libraries must not corrupt the wire protocol or log PDF text.
    with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        options = json.loads(sys.stdin.readline())
        try:
            engine = create_engine(options)
        except ValueError as error:
            wire.write(json.dumps({"error": str(error)}) + "\n")
            wire.flush()
            return
        for line in sys.stdin:
            try:
                response = recognize_page(engine, options, json.loads(line))
            except Exception as error:
                message = "OCR could not process this page. Check the PDF and retry."
                if isinstance(error, ValueError) and str(error) == "PDF exceeds the configured extracted text limit":
                    message = str(error)
                response = {"error": message}
            wire.write(json.dumps(response, ensure_ascii=True) + "\n")
            wire.flush()
            if "error" in response:
                return


if __name__ == "__main__":
    main()
