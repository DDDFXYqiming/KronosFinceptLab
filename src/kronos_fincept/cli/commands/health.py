"""kronos health — Runtime health checks."""

from __future__ import annotations

import click

from kronos_fincept.api.deps import get_model_info
from kronos_fincept.build_info import get_build_info
from kronos_fincept.cli.output import output_json, output_table


@click.command("health")
@click.option("--deep", is_flag=True, default=False, help="Run deep model/runtime diagnostics")
@click.pass_context
def health_cmd(ctx: click.Context, deep: bool) -> None:
    """Show API-compatible health diagnostics."""
    output_format = ctx.obj.get("output_format", "json")
    model_info = get_model_info(deep=deep)
    build_info = get_build_info()
    result = {
        "status": model_info["status"],
        "version": "2.0.0",
        "app_version": build_info.app_version,
        "build_commit": build_info.build_commit,
        "build_ref": build_info.build_ref,
        "build_source": build_info.build_source,
        "model_loaded": model_info["model_loaded"],
        "model_id": model_info["model_id"],
        "tokenizer_id": model_info["tokenizer_id"],
        "device": model_info["device"],
        "uptime_seconds": 0.0,
        "runtime_mode": model_info["runtime_mode"],
        "model_enabled": model_info["model_enabled"],
        "deep_check": model_info["deep_check"],
        "capabilities": model_info["capabilities"],
        "model_error": model_info["model_error"],
    }
    if output_format == "json":
        output_json(result)
    else:
        output_table(
            "[health] KronosFinceptLab",
            ["Field", "Value"],
            [[key, str(value)] for key, value in result.items() if key != "capabilities"],
        )
