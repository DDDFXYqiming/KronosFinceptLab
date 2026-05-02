"""Click CLI entry point for KronosFinceptLab.

Usage:
    kronos --output json forecast --symbol 600036 --pred-len 5
    kronos batch --symbols 600036,000858 --pred-len 5
    kronos data fetch --symbol 600036 --start 20240101 --end 20260430
    kronos data search --q 招商银行
    kronos backtest ranking --symbols 600036,000858 --start 20250101 --end 20260430
    kronos serve --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

from importlib import import_module

import click

from kronos_fincept.logging_config import configure_logging


COMMANDS = {
    "forecast": ("kronos_fincept.cli.commands.forecast", "forecast_cmd"),
    "batch": ("kronos_fincept.cli.commands.batch", "batch_cmd"),
    "data": ("kronos_fincept.cli.commands.data", "data_group"),
    "backtest": ("kronos_fincept.cli.commands.backtest", "backtest_group"),
    "serve": ("kronos_fincept.cli.commands.serve", "serve_cmd"),
    "analyze": ("kronos_fincept.cli.commands.analyze", "analyze_group"),
    "alert": ("kronos_fincept.cli.commands.alert", "alert_group"),
}


class LazyCLI(click.Group):
    """Click group that imports subcommands only when they are requested."""

    def list_commands(self, ctx: click.Context) -> list[str]:
        return sorted(COMMANDS)

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        command_spec = COMMANDS.get(cmd_name)
        if command_spec is None:
            return None

        module_name, attr_name = command_spec
        module = import_module(module_name)
        return getattr(module, attr_name)


@click.group(cls=LazyCLI)
@click.option("--output", "output_format", type=click.Choice(["json", "table"]), default="json",
              help="Output format (default: json)")
@click.option("--verbose", is_flag=True, default=False, help="Verbose output")
@click.pass_context
def cli(ctx: click.Context, output_format: str, verbose: bool) -> None:
    """KronosFinceptLab — Financial quantitative analysis platform."""
    configure_logging(level="DEBUG" if verbose else None)
    ctx.ensure_object(dict)
    ctx.obj["output_format"] = output_format
    ctx.obj["verbose"] = verbose


def main(argv: list[str] | None = None) -> int:
    """Entry point for the kronos command."""
    return cli(standalone_mode=False, args=argv) or 0


if __name__ == "__main__":
    cli()
