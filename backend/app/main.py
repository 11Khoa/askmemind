import logging
from time import perf_counter

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request

from app import models
from app.core.config import settings
from app.core.logging import (
    configure_logging,
    finish_request_context,
    get_request_id,
    log_event,
    start_request_context,
)
from app.routers import auth, chat, document, upload

configure_logging(level=settings.log_level)
logger = logging.getLogger(__name__)
app = FastAPI()


@app.middleware("http")
async def request_observability_middleware(request: Request, call_next):
    context_tokens = start_request_context(
        request_id=request.headers.get("X-Request-ID"),
    )
    started_at = perf_counter()

    try:
        response = await call_next(request)
        duration_ms = (perf_counter() - started_at) * 1000
        log_event(
            logger,
            logging.INFO,
            "http.request.completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round(duration_ms, 2),
        )
        response.headers["X-Request-ID"] = get_request_id() or ""
        return response
    except Exception:
        duration_ms = (perf_counter() - started_at) * 1000
        logger.exception(
            "http.request.failed",
            extra={
                "event_data": {
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round(duration_ms, 2),
                }
            },
        )
        raise
    finally:
        finish_request_context(context_tokens)


cors_origins = [
    origin.strip()
    for origin in settings.backend_cors_origins.split(",")
    if origin.strip()
]

if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(upload.router)
app.include_router(document.router)
