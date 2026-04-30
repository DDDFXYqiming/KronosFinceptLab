"""kronos serve — Start FastAPI server.

Examples:
    kronos serve
    kronos serve --host 0.0.0.0 --port 8000
    kronos serve --host 0.0.0.0 --port 8000 --workers 4
"""

from __future__ import annotations

import click


@click.command("serve")
@click.option("--host", type=str, default="0.0.0.0", help="Bind host")
@click.option("--port", type=int, default=8000, help="Bind port")
@click.option("--workers", type=int, default=1, help="Number of workers")
@click.option("--reload", is_flag=True, default=False, help="Auto-reload on code changes")
def serve_cmd(host: str, port: int, workers: int, reload: bool) -> None:
    """Start the FastAPI API server."""
    import uvicorn
    click.echo(f"[launch] Starting KronosFinceptLab API on {host}:{port}")
    click.echo(f"   Docs: http://{host}:{port}/docs")
    uvicorn.run(
        "kronos_fincept.api.app:app",
        host=host,
        port=port,
        workers=workers,
        reload=reload,
        log_level="info",
    )
