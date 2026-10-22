import logging
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request

from app import models
from app.core.config import Settings, settings
from app.core.logging import (
    configure_logging,
    finish_request_context,
    get_request_id,
    log_event,
    start_request_context,
)
from app.routers import auth, chat, document, health, upload
from app.services.token_store import TokenStoreUnavailable

configure_logging(level=settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Celery jobs survive API restarts. Do not fail work owned by another process.
    yield


app = FastAPI(lifespan=lifespan)


@app.exception_handler(TokenStoreUnavailable)
async def token_store_unavailable_handler(
    request: Request, error: TokenStoreUnavailable
):
    log_event(logger, logging.ERROR, "auth.token_store.unavailable")
    return JSONResponse(
        status_code=503, content={"detail": "Authentication temporarily unavailable"}
    )


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
        if request.url.path.startswith("/auth/"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
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


def configure_cors(application: FastAPI, config: Settings) -> None:
    if config.cors_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=config.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=[
                "Authorization",
                "Content-Type",
                "X-CSRF-Protection",
                "X-Request-ID",
            ],
            expose_headers=["X-Request-ID"],
        )


configure_cors(app, settings)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(upload.router)
app.include_router(document.router)
