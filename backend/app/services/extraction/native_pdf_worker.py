"""Private protocol: no network, application settings, secrets or document logs."""
import contextlib
import json
import math
import os
import sys
from app.services.extraction.ocr_worker import exit_if_parent_dies


def needs_ocr(page, text):
    if not text:
        return bool(page.get_bboxlog())
    if len(text) >= 80:
        return False
    import fitz
    area = page.rect.get_area()
    return area > 0 and any((fitz.Rect(image["bbox"]) & page.rect).get_area() / area >= .25
                           for image in page.get_image_info())


def main():
    exit_if_parent_dies()
    options = json.loads(sys.stdin.readline())
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[name] = "1"
    if sys.platform == "linux":
        import resource
        cpu = math.ceil(options["cpu_seconds"]) + 1
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
    wire = sys.stdout
    with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        try:
            import fitz
            if sys.platform == "linux":
                # Trusted shared libraries reserve large virtual ranges. Limit
                # additional address space before touching the untrusted PDF.
                from pathlib import Path
                baseline = int(Path("/proc/self/statm").read_text().split()[0]) * os.sysconf("SC_PAGE_SIZE")
                ceiling = baseline + options["memory_mb"] * 1024 * 1024
                resource.setrlimit(resource.RLIMIT_AS, (ceiling, ceiling))
            with fitz.open(options["file_path"]) as document:
                for line in sys.stdin:
                    request = json.loads(line)
                    if request["action"] == "info":
                        result = {"page_count": document.page_count}
                    else:
                        page = document.load_page(request["page_index"])
                        text = page.get_text().strip()
                        if len(text) > request["max_characters"]:
                            raise ValueError("PDF exceeds the configured extracted text limit")
                        result = {"text": text, "needs_ocr": needs_ocr(page, text)}
                    wire.write(json.dumps(result, ensure_ascii=True) + "\n"); wire.flush()
        except Exception as error:
            message = "Could not parse PDF within the configured resource limits"
            if isinstance(error, ValueError) and str(error) == "PDF exceeds the configured extracted text limit":
                message = str(error)
            wire.write(json.dumps({"error": message}) + "\n"); wire.flush()


if __name__ == "__main__":
    main()
