"""kronos suggestions — Generate Web/API-aligned prompt suggestions."""

from __future__ import annotations

import asyncio
import logging

import click

from kronos_fincept.cli.output import output_json, output_table


@click.command("suggestions")
@click.option("--type", "question_type", type=click.Choice(["analysis", "macro"]), default="analysis", help="Suggestion type")
@click.pass_context
def suggestions_cmd(ctx: click.Context, question_type: str) -> None:
    """Generate financial question suggestions using the API route logic."""
    output_format = ctx.obj.get("output_format", "json")
    from kronos_fincept.api.routes.suggestions import get_suggestions

    route_logger = logging.getLogger("kronos_fincept.api.routes.suggestions")
    was_disabled = route_logger.disabled
    route_logger.disabled = True
    try:
        result = asyncio.run(get_suggestions(type=question_type))
    finally:
        route_logger.disabled = was_disabled
    payload = {"ok": True, "type": question_type, **result}
    if output_format == "json":
        output_json(payload)
    else:
        rows = [[str(i), question] for i, question in enumerate(payload.get("questions", []), 1)]
        output_table(f"[suggestions] {question_type}", ["#", "Question"], rows)
