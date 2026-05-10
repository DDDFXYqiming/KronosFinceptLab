"""FastAPI application entry point for KronosFinceptLab."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from kronos_fincept.api.routes import backtest, batch, data, forecast, health, analyze, ai_analyze, alert, suggestions
from kronos_fincept.config import settings
from kronos_fincept.logging_config import (
    configure_logging,
    log_event,
    reset_request_id,
    reset_test_run_id,
    set_request_id,
    set_test_run_id,
)

logger = logging.getLogger("kronos_fincept.api")

# Track server start time for uptime calculation
_start_time: float = 0.0


def _start_kronos_prewarm_thread() -> None:
    """Warm the single configured Kronos model in the background after API startup."""
    if not settings.kronos.enable_real_model or not settings.kronos.prewarm_on_startup:
        return

    def _run() -> None:
        try:
            from kronos_fincept.service import prewarm_default_predictor

            prewarm_default_predictor()
        except Exception:
            log_event(
                logger,
                logging.WARNING,
                "api.kronos.prewarm_failed",
                "Kronos model prewarm failed; first forecast request will retry lazy loading",
                exc_info=True,
            )

    thread = threading.Thread(target=_run, name="kronos-prewarm", daemon=True)
    thread.start()
    log_event(
        logger,
        logging.INFO,
        "api.kronos.prewarm_started",
        "Kronos model prewarm started in background",
        model_id=settings.kronos.model_id,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler — startup and shutdown."""
    global _start_time
    _start_time = time.time()
    log_event(logger, logging.INFO, "api.startup", "KronosFinceptLab API starting up")
    _start_kronos_prewarm_thread()
    yield
    log_event(logger, logging.INFO, "api.shutdown", "KronosFinceptLab API shutting down")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    configure_logging()
    app = FastAPI(
        title="KronosFinceptLab API",
        description="Financial quantitative analysis platform powered by Kronos foundation models.",
        version="2.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # CORS — allow Next.js frontend and local dev
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3001",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request logging middleware
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        test_run_id = request.headers.get("X-Test-Run-ID")
        request.state.request_id = request_id
        request.state.test_run_id = test_run_id
        token = set_request_id(request_id)
        test_token = set_test_run_id(test_run_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            response.headers["X-Request-ID"] = request_id
            if test_run_id:
                response.headers["X-Test-Run-ID"] = test_run_id
            log_event(
                logger,
                logging.INFO,
                "api.request",
                f"{request.method} {request.url.path} -> {response.status_code}",
                request_id=request_id,
                test_run_id=test_run_id,
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                client=request.client.host if request.client else None,
                duration_ms=elapsed_ms,
            )
            return response
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            log_event(
                logger,
                logging.ERROR,
                "api.request.error",
                f"{request.method} {request.url.path} failed",
                request_id=request_id,
                test_run_id=test_run_id,
                method=request.method,
                path=request.url.path,
                client=request.client.host if request.client else None,
                duration_ms=elapsed_ms,
                error_type=type(exc).__name__,
            )
            raise
        finally:
            reset_request_id(token)
            reset_test_run_id(test_token)

    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        request_id = request.headers.get("X-Request-ID") or getattr(request.state, "request_id", None)
        test_run_id = request.headers.get("X-Test-Run-ID") or getattr(request.state, "test_run_id", None)
        log_event(
            logger,
            logging.ERROR,
            "api.unhandled_exception",
            f"Unhandled exception on {request.method} {request.url.path}",
            request_id=request_id,
            test_run_id=test_run_id,
            method=request.method,
            path=request.url.path,
            error_type=type(exc).__name__,
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": "Internal server error",
                "request_id": request_id,
            },
            headers={
                "X-Request-ID": request_id or "",
                **({"X-Test-Run-ID": test_run_id} if test_run_id else {}),
            },
        )

    # Register routes
    app.include_router(health.router, prefix="/api", tags=["health"])
    app.include_router(forecast.router, prefix="/api", tags=["forecast"])
    app.include_router(batch.router, prefix="/api", tags=["batch"])
    app.include_router(data.router, prefix="/api", tags=["data"])
    app.include_router(backtest.router, prefix="/api", tags=["backtest"])
    app.include_router(analyze.router, tags=["analysis"])
    app.include_router(ai_analyze.router, tags=["analysis"])
    app.include_router(alert.router, prefix="/api", tags=["alert"])
    app.include_router(suggestions.router, tags=["suggestions"])

    # Expose start_time for health endpoint
    app.state.start_time = _start_time

    return app


# Default app instance for uvicorn
app = create_app()


def main():
    """Entry point for `kronos-api` command."""
    import uvicorn
    uvicorn.run(
        "kronos_fincept.api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
