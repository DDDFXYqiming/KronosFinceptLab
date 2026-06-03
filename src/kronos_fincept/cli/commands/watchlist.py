"""kronos watchlist — Watchlist management commands.

Examples:
    kronos watchlist list
    kronos watchlist create --name MyPortfolio --symbols 600036,000858 --market cn
    kronos watchlist delete abc123
    kronos watchlist research --name MyPortfolio --symbols 600036,000858
"""

from __future__ import annotations

import asyncio

import click

from kronos_fincept.cli.output import output_json, output_table


@click.group("watchlist")
def watchlist_group() -> None:
    """Manage watchlists and portfolio research."""
    pass


@watchlist_group.command("list")
@click.pass_context
def list_cmd(ctx: click.Context) -> None:
    """List all watchlists."""
    from kronos_fincept.api.routes.watchlist import list_watchlists

    output_format = ctx.obj.get("output_format", "json")
    response = asyncio.run(list_watchlists())
    payload = response.model_dump() if hasattr(response, "model_dump") else response.dict()

    if output_format == "json":
        output_json(payload)
        return

    watchlists = payload.get("watchlists", [])
    if not watchlists:
        click.echo("No watchlists found.")
        return

    rows = []
    for wl in watchlists:
        rows.append([
            wl.get("id", "")[:12],
            wl.get("name", ""),
            wl.get("market", ""),
            ",".join(wl.get("symbols", [])),
            str(len(wl.get("symbols", []))),
        ])
    output_table(
        "Watchlists",
        ["ID", "Name", "Market", "Symbols", "Count"],
        rows,
    )


@watchlist_group.command("create")
@click.option("--name", "-n", required=True, help="Watchlist name")
@click.option("--symbols", "-s", required=True, help="Comma-separated symbols")
@click.option("--market", "-m", default="cn", help="Market: cn, us, hk (default: cn)")
@click.option("--tags", default="", help="Comma-separated tags")
@click.option("--note", default=None, help="Optional note")
@click.pass_context
def create_cmd(
    ctx: click.Context,
    name: str,
    symbols: str,
    market: str,
    tags: str,
    note: str | None,
) -> None:
    """Create a new watchlist."""
    from kronos_fincept.api.routes.watchlist import WatchlistListIn, create_watchlist

    output_format = ctx.obj.get("output_format", "json")
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    if not symbol_list:
        click.echo("Error: --symbols cannot be empty", err=True)
        raise SystemExit(1)

    req = WatchlistListIn(
        name=name,
        market=market,
        symbols=symbol_list,
        tags=tag_list,
        note=note,
    )
    response = asyncio.run(create_watchlist(req))
    payload = response.model_dump() if hasattr(response, "model_dump") else response.dict()

    if output_format == "json":
        output_json(payload)
    else:
        click.echo(f"Watchlist created: {payload.get('id')}")
        click.echo(f"  Name:    {payload.get('name')}")
        click.echo(f"  Market:  {payload.get('market')}")
        click.echo(f"  Symbols: {', '.join(payload.get('symbols', []))}")


@watchlist_group.command("delete")
@click.argument("watchlist_id", type=str)
@click.pass_context
def delete_cmd(ctx: click.Context, watchlist_id: str) -> None:
    """Delete a watchlist by ID."""
    from kronos_fincept.api.routes.watchlist import delete_watchlist

    output_format = ctx.obj.get("output_format", "json")
    response = asyncio.run(delete_watchlist(watchlist_id))
    payload = response.model_dump() if hasattr(response, "model_dump") else response.dict()

    if output_format == "json":
        output_json(payload)
    else:
        if payload.get("deleted"):
            click.echo(f"Watchlist deleted: {watchlist_id}")
        else:
            click.echo(f"Failed to delete watchlist: {watchlist_id}")


@watchlist_group.command("research")
@click.option("--name", "-n", default="Watchlist", help="Watchlist name for research")
@click.option("--symbols", "-s", required=True, help="Comma-separated symbols")
@click.pass_context
def research_cmd(ctx: click.Context, name: str, symbols: str) -> None:
    """Run portfolio research on a set of symbols."""
    from kronos_fincept.api.routes.watchlist import WatchlistResearchRequest, watchlist_research

    output_format = ctx.obj.get("output_format", "json")
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]

    if not symbol_list:
        click.echo("Error: --symbols cannot be empty", err=True)
        raise SystemExit(1)

    req = WatchlistResearchRequest(name=name, symbols=symbol_list)
    response = asyncio.run(watchlist_research(req))
    payload = response.model_dump() if hasattr(response, "model_dump") else response.dict()

    if output_format == "json":
        output_json(payload)
    else:
        click.echo(f"Watchlist Research: {payload.get('name')}")
        click.echo(f"  Symbols: {payload.get('symbol_count')}")
        click.echo(f"  Expected Return: {payload.get('expected_return', 0):.4%}")
        click.echo(f"  Top Symbols: {', '.join(payload.get('top_symbols', []))}")
        if payload.get("risk_flags"):
            click.echo(f"  Risk Flags:")
            for flag in payload["risk_flags"]:
                click.echo(f"    - {flag}")
        click.echo("\n  [warn] Research use only, not investment advice.")
