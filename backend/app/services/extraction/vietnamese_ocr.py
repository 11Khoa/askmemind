"""RapidOCR line detection/orientation with Vietnamese-capable ONNX recognition.

Stock Latin CTC vocabularies omit Vietnamese tone letters. VietOCR's explicit
vocabulary contains them; its encoder/decoder run with ONNX Runtime only.
"""

import json
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image


def validate_vocabulary(metadata):
    required = set("ăâđêôơưàảãáạằẳẵắặầẩẫấậèẻẽéẹềểễếệìỉĩíịòỏõóọồổỗốộờởỡớợùủũúụừửữứựỳỷỹýỵ")
    if not required.issubset(set(metadata.get("vocab", ""))):
        raise ValueError("OCR vocabulary does not support Vietnamese tone marks")


class VietnameseOCREngine:
    def __init__(self, paths, threads):
        import cv2
        import onnxruntime as ort
        import rapidocr
        from rapidocr.ch_ppocr_det import TextDetector
        from rapidocr.ch_ppocr_cls import TextClassifier
        from rapidocr.utils.parse_parameters import ParseParams

        self.metadata = json.loads(paths["vocab"].read_text(encoding="utf-8"))
        validate_vocabulary(self.metadata)
        self.characters = {index + self.metadata["offset"]: char
                           for index, char in enumerate(self.metadata["vocab"])}
        cv2.setNumThreads(threads)
        ort.disable_telemetry_events()
        session_options = ort.SessionOptions()
        session_options.intra_op_num_threads = threads
        session_options.inter_op_num_threads = 1
        session_options.enable_cpu_mem_arena = False
        self.encoder = ort.InferenceSession(str(paths["encoder"]), sess_options=session_options,
                                           providers=["CPUExecutionProvider"])
        self.decoder = ort.InferenceSession(str(paths["decoder"]), sess_options=session_options,
                                           providers=["CPUExecutionProvider"])
        cfg = ParseParams.load(Path(rapidocr.__file__).parent / "config.yaml")
        cfg = ParseParams.update_batch(cfg, {
            "Det.model_path": str(paths["det"]), "Cls.model_path": str(paths["cls"]),
            "Det.limit_type": "max",  # Never upscale the short side of a thin page to 736px.
            "Det.unclip_ratio": 2.0,  # Leave room for Vietnamese marks above/below letters.
            "Cls.cls_batch_num": 1,
            "EngineConfig.onnxruntime.intra_op_num_threads": threads,
            "EngineConfig.onnxruntime.inter_op_num_threads": 1,
            "EngineConfig.onnxruntime.enable_cpu_mem_arena": False,
        })
        for section in (cfg.Det, cfg.Cls):
            section.engine_cfg = cfg.EngineConfig[section.engine_type.value]
        self.detector = TextDetector(cfg.Det)
        self.classifier = TextClassifier(cfg.Cls)

    def read_line(self, bgr):
        meta = self.metadata
        height, width = bgr.shape[:2]
        if height <= 0 or width <= 0:
            return "", 0.0
        target_width = int(math.ceil(int(meta["image_height"] * width / height) / 10) * 10)
        target_width = min(max(target_width, meta["image_min_width"]), meta["image_max_width"])
        image = Image.fromarray(bgr[:, :, ::-1]).resize(
            (target_width, meta["image_height"]), Image.Resampling.LANCZOS,
        )
        tensor = np.asarray(image, dtype=np.float32).transpose(2, 0, 1)[None] / 255.0
        hidden, encoder_output = self.encoder.run(None, {"image": tensor})
        token = np.array([meta["sos"]], dtype=np.int64)
        text, log_probabilities = [], []
        for _ in range(meta["max_seq_length"]):
            logp, hidden = self.decoder.run(None, {
                "tgt": token, "hidden": hidden, "encoder_outputs": encoder_output,
            })
            token = logp.argmax(-1).astype(np.int64)
            index = int(token[0])
            if index == meta["eos"]:
                score = math.exp(float(np.mean(log_probabilities))) if log_probabilities else 0.0
                return "".join(text), min(1.0, score)
            if index not in self.characters:
                return "", 0.0
            text.append(self.characters[index])
            log_probabilities.append(float(logp[0, index]))
        # Do not return a plausible-looking truncated line without an EOS.
        return "", 0.0

    def __call__(self, image, text_score=0.6):
        from rapidocr.utils import get_rotate_crop_image

        if min(image.shape[:2]) < 32:
            return SimpleNamespace(txts=(), scores=())
        detected = self.detector(image)
        texts, scores = [], []
        if detected.boxes is not None:
            for box in detected.boxes:
                crop = get_rotate_crop_image(image, box.copy())
                oriented = self.classifier([crop]).img_list[0]
                text, score = self.read_line(oriented)
                if score >= text_score:
                    texts.append(text)
                    scores.append(score)
        return SimpleNamespace(txts=tuple(texts), scores=tuple(scores))
