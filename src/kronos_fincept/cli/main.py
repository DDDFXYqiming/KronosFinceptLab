"""Click CLI entry point for KronosFinceptLab.

Usage:
    kronos forecast --symbol 600519 --pred-len 5 --output json
    kronos batch --symbols 600519,000858 --pred-len 5
    kronos data fetch --symbol 600519 --start 20240101 --end 20260430
    kronos data search --q 茅台
    kronos backtest ranking --symbols 600519,000858 --start 20250101 --end 20260430
    kronos serve --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import click

from kronos_fincept.cli.commands import forecast, batch, data, backtest, serve, analyze


@click.group()
@click.option("--output", "output_format", type=click.Choice(["json", "table"]), default="json",
              help="Output format (default: json)")
@click.option("--verbose", is_flag=True, default=False, help="Verbose output")
@click.pass_context
def cli(ctx: click.Context, output_format: str, verbose: bool) -> None:
    """KronosFinceptLab — Financial quantitative analysis platform."""
    ctx.ensure_object(dict)
    ctx.obj["output_format"] = output_format
    ctx.obj["verbose"] = verbose


# Register subcommands
cli.add_command(forecast.forecast_cmd, "forecast")
cli.add_command(batch.batch_cmd, "batch")
cli.add_command(data.data_group, "data")
cli.add_command(backtest.backtest_group, "backtest")
cli.add_command(serve.serve_cmd, "serve")
cli.add_command(analyze.analyze_group, "analyze")


def main(argv: list[str] | None = None) -> int:
    """Entry point for the kronos command."""
    return cli(standalone_mode=False, args=argv) or 0


if __name__ == "__main__":
    cli()
