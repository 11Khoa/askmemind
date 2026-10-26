# Scanned PDF ingestion

PDF extraction uses RapidOCR 3.4.1 and CPU ONNX Runtime 1.23.2. It runs locally:
document images/text are not sent to an OCR service. RapidOCR supplies PP-OCRv4
line detection and 180-degree orientation classification. VietOCR vgg_seq2seq
ONNX encoder/decoder models recognize Vietnamese and English. No PyTorch or
Tesseract executable is required. The originally selected stock Latin CTC model
omits Vietnamese tone letters and is no longer used.

## Deployment

Install `backend/requirements.txt`, then from `backend/` run:

```sh
python -m app.commands.prepare_ocr_models
python -m app.commands.check_pdf_ocr
```

The preparation command requires outbound HTTPS to `github.com` and GitHub
release asset hosts for recognition models. Detector/classifier fallback
downloads use `www.modelscope.cn` and its artifact CDN. Preserve TLS verification.
It copies matching detector/classifier models from the RapidOCR wheel, downloads
the VietOCR encoder/decoder/vocabulary, verifies all five SHA-256 digests, and atomically installs
them. Existing mismatched files cause a failure; do not replace the expected
digests to accommodate corrupted downloads. Remove the bad artifact and prepare
again. The checksums and versioned URLs come from the upstream
[v3.4.1 model manifest](https://github.com/RapidAI/RapidOCR/blob/v3.4.1/python/rapidocr/default_models.yaml)
and the published [VietOCR ONNX ocr-v1 release asset digests](https://github.com/duchoa1297/vietocr-onnx/releases/tag/ocr-v1).
Model binaries are ignored by Git. Retain upstream license notices when
redistributing models; see RapidOCR, PaddleOCR and
[pbcquoc/VietOCR](https://github.com/pbcquoc/vietocr) (Apache-2.0).

The Dockerfile provisions the same models under `/opt/askmemind/ocr-models` during
the build and installs OpenCV's shared-library prerequisites. Local development
defaults to `backend/models/ocr/`. Set `PDF_OCR_MODEL_DIR` to use a different
directory and pass `--output` to the preparation command, or export that variable
before running it. Mount the model directory read-only at runtime. Run the smoke
test in the built image before rolling out to workers. Runtime inference uses
verified local ONNX sessions and a checked Vietnamese vocabulary; it never auto-downloads
missing models or silently falls back to a Chinese recognizer.
Only RapidOCR's detection/classification components are instantiated. No
visualizer or stock recognizer is loaded, so inference never downloads a font.
Recognition assets total about 85 MiB on disk. A synthetic two-scan-page run on
the development cloud with one thread, 150 DPI and a two-million-pixel cap took
about 4.2 seconds including initialization and peaked at roughly 775 MiB RSS in
the OCR subprocess; this is an observation, not a VPS
capacity guarantee. Use one Celery worker and one OCR thread on a small VPS,
and measure peak memory with real documents before rollout.

## Processing and limits

- Native text pages keep the existing extraction path. Truly blank pages skip OCR.
- Pages with visual content but no text are rendered and recognized. A large
  image covering at least 25% of a page with fewer than 80 text characters also
  triggers OCR, covering scans with a short selectable header.
- OCR replaces the page text instead of appending duplicate headers. If no text
  passes the confidence threshold, any original native text is retained.
- PDF page numbers stay one-based through extraction, chunking and citations.
  Chunk metadata records `extraction_method=ocr` and average retained-line
  confidence. Confidence is an OCR score, not a measure of answer correctness.
- A lazy child interpreter handles OCR pages sequentially and reuses its engine
  within one document. It runs under Celery prefork without spawning Python
  multiprocessing children. The parent kills and reaps it on success or error,
  including native inference timeout. Each document initializes its own engine;
  bound Celery concurrency to fit your CPU and memory budget.
  Compose defaults to two worker processes (`CELERY_WORKER_CONCURRENCY=2`) and
  recycles each worker after 20 tasks.
- The raster is RGB/BGR, without alpha, downscaled to stay under the pixel cap.
  Its longest side is capped at 4096 pixels, including extreme-aspect-ratio pages.
  Recognition processes one detected line at a time using CPU-only sessions.
  Autoregressive decoding is capped at the pinned vocabulary's sequence limit;
  a line without an end token is rejected rather than returned as truncated text.
  Limits bound OCR
  work; set container memory/CPU limits too (pixels are not a hard RSS limit).

| Variable | Default | Purpose |
|---|---:|---|
| `PDF_OCR_ENABLED` | `True` | OCR fallback; disable to restore text-only ingestion |
| `PDF_OCR_DPI` | `180` | Requested render resolution, subject to pixel cap |
| `PDF_OCR_MAX_PIXELS` | `8000000` | Max rendered pixels per OCR page |
| `PDF_OCR_MAX_PAGES` | `50` | Max OCR attempts per document, including empty scans |
| `PDF_OCR_PAGE_TIMEOUT_SECONDS` | `60` | Per OCR request, including first model initialization |
| `PDF_OCR_DOCUMENT_TIMEOUT_SECONDS` | `300` | Shared OCR deadline from extraction start |
| `PDF_OCR_MIN_CONFIDENCE` | `0.6` | Minimum retained line score |
| `PDF_OCR_THREADS` | `2` | Intra-op/OpenCV CPU threads; ONNX inter-op uses one |

Existing `MAX_PDF_PAGES` and `MAX_PDF_TEXT_CHARACTERS` also apply. Exceeding a
limit, a missing/corrupt model, worker crash or timeout fails ingestion rather
than marking a partially extracted document ready. The existing document retry
flow can re-run extraction after fixing the cause; this change does not add an
unbounded automatic retry loop. Completed chunk/embedding checkpoints still use
the existing recovery behavior. Restarting a completed document does not rerun
OCR unless the extraction checkpoint is rebuilt.

`pdf.extraction.completed` logs counts, duration and page numbers for OCR pages
with no confident text, without recording document text. Empty scan pages can be
blank or unreadable; they are omitted and reported in `empty_ocr_pages` extraction
metadata/logs. They are not automatically deemed an OCR failure when other pages
contain text. Inspect this signal when validating real customer documents.

## Validation and rollout

The real-model smoke command constructs image-only English/Vietnamese pages,
checks diacritic-bearing keywords, mixes in a native text page and blank page,
and verifies page metadata through chunking. It uses no embedding/LLM API calls.
Unit tests additionally cover confidence filtering, rendering limits, model
integrity, timeout/crash cleanup, disabling OCR and failure propagation.

Before rollout, run the smoke test on the target image/CPU and evaluate a
representative set of real scans. Measure OCR accuracy, ingestion latency/RSS,
retrieval quality and citation pages. A synthetic smoke test does not certify
handwriting, complex tables/multicolumn reading order, arbitrary rotation,
poor-quality scans or math recognition. This implementation produces plain text,
not layout/table reconstruction or PDF coordinate highlights. It does not OCR
image sections on otherwise text-rich pages (80+ native characters); tune or
extend page selection separately if that is required.

Roll back by setting `PDF_OCR_ENABLED=False` and restarting workers. Newly
uploaded scans will then follow the previous text-only behavior; existing chunks
and original PDFs are not changed.
