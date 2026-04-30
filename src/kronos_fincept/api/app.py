"""FastAPI application entry point for KronosFinceptLab."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from kronos_fincept.api.routes import backtest, batch, data, forecast, health, analyze

logger = logging.getLogger("kronos_fincept.api")

# Track server start time for uptime calculation
_start_time: float = 0.0


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler — startup and shutdown."""
    global _start_time
    _start_time = time.time()
    logger.info("KronosFinceptLab API starting up...")
    yield
    logger.info("KronosFinceptLab API shutting down.")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
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
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "%s %s -> %d (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response

    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": f"Internal server error: {type(exc).__name__}: {str(exc)}",
            },
        )

    # Register routes
    app.include_router(health.router, prefix="/api", tags=["health"])
    app.include_router(forecast.router, prefix="/api", tags=["forecast"])
    app.include_router(batch.router, prefix="/api", tags=["batch"])
    app.include_router(data.router, prefix="/api", tags=["data"])
    app.include_router(backtest.router, prefix="/api", tags=["backtest"])
    app.include_router(analyze.router, tags=["analysis"])

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
