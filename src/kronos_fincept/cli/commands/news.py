"""kronos news - RSS/Atom news helpers."""

from __future__ import annotations

import asyncio
from typing import Any

import click

from kronos_fincept.cli.output import output_json, output_table


@click.group("news")
def news_group() -> None:
    """Fetch HTTPS RSS/Atom news feeds."""


def _parse_feed_arg(value: str) -> dict[str, Any]:
    parts = [part.strip() for part in value.split("|", 2)]
    if len(parts) == 3:
        return {"id": parts[0] or None, "title": parts[1] or None, "url": parts[2]}
    return {"url": value.strip()}


@news_group.command("rss")
@click.option(
    "--feed",
    "feeds",
    multiple=True,
    required=True,
    help="Feed URL, or id|title|url. Repeat for multiple feeds.",
)
@click.option("--limit", "limit_per_feed", type=int, default=8, show_default=True, help="Items per feed")
@click.option("--json", "as_json", is_flag=True, default=False, help="Force JSON output")
@click.pass_context
def news_rss(ctx: click.Context, feeds: tuple[str, ...], limit_per_feed: int, as_json: bool) -> None:
    """Fetch and normalize HTTPS RSS/Atom feeds."""
    from kronos_fincept.api.routes.news import RssFetchRequest, fetch_rss

    req = RssFetchRequest(
        feeds=[_parse_feed_arg(item) for item in feeds],
        limit_per_feed=limit_per_feed,
    )
    response = asyncio.run(fetch_rss(req))
    payload = response.model_dump() if hasattr(response, "model_dump") else response.dict()

    if as_json or ctx.obj.get("output_format", "json") == "json":
        output_json(payload)
        return

    rows = [
        [
            item.get("feed_title", ""),
            item.get("published_at", ""),
            item.get("title", ""),
            item.get("url", ""),
        ]
        for item in payload.get("items", [])[:40]
    ]
    output_table("[news/rss]", ["Feed", "Published", "Title", "URL"], rows)
    if payload.get("errors"):
        click.echo("")
        click.echo("Errors:")
        for feed_id, error in payload["errors"].items():
            click.echo(f"- {feed_id}: {error}")
