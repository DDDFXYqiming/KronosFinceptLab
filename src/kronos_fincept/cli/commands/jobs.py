"""kronos jobs — Job management commands.

Examples:
    kronos jobs list
    kronos jobs list --limit 10 --status running --kind forecast
    kronos jobs show abc123def456
    kronos jobs cancel abc123def456
"""

from __future__ import annotations

import asyncio

import click

from kronos_fincept.cli.output import output_json, output_table


@click.group("jobs")
def jobs_group() -> None:
    """Manage background jobs."""
    pass


@jobs_group.command("list")
@click.option("--limit", "-n", type=int, default=50, help="Max jobs to list (default: 50)")
@click.option("--status", type=str, default=None, help="Filter by status: queued, running, completed, failed, cancelled")
@click.option("--kind", type=str, default=None, help="Filter by kind: forecast, analyze, batch, backtest")
@click.pass_context
def list_cmd(ctx: click.Context, limit: int, status: str | None, kind: str | None) -> None:
    """List background jobs."""
    from kronos_fincept.api.routes.jobs import list_jobs

    output_format = ctx.obj.get("output_format", "json")
    response = asyncio.run(list_jobs(limit=limit, status=status, kind=kind))
    payload = response.model_dump() if hasattr(response, "model_dump") else response.dict()

    if output_format == "json":
        output_json(payload)
        return

    jobs = payload.get("jobs", [])
    if not jobs:
        click.echo("No jobs found.")
        return

    rows = []
    for job in jobs:
        rows.append([
            job.get("job_id", "")[:12],
            job.get("kind", ""),
            job.get("status", ""),
            str(len(job.get("steps", []))),
            job.get("error", "")[:40] if job.get("error") else "",
        ])
    output_table(
        f"Jobs (total: {payload.get('total', len(jobs))})",
        ["ID", "Kind", "Status", "Steps", "Error"],
        rows,
    )


@jobs_group.command("show")
@click.argument("job_id", type=str)
@click.pass_context
def show_cmd(ctx: click.Context, job_id: str) -> None:
    """Show job status and details."""
    from kronos_fincept.api.routes.jobs import get_job

    output_format = ctx.obj.get("output_format", "json")
    response = asyncio.run(get_job(job_id))
    payload = response.model_dump() if hasattr(response, "model_dump") else response.dict()

    if output_format == "json":
        output_json(payload)
    else:
        click.echo(f"Job: {payload.get('job_id')}")
        click.echo(f"  Kind:    {payload.get('kind')}")
        click.echo(f"  Status:  {payload.get('status')}")
        click.echo(f"  Created: {payload.get('created_at')}")
        click.echo(f"  Updated: {payload.get('updated_at')}")
        if payload.get("error"):
            click.echo(f"  Error:   {payload['error']}")
        click.echo("\n  Steps:")
        for i, step in enumerate(payload.get("steps", []), 1):
            click.echo(f"    {i}. [{step.get('status')}] {step.get('name')}: {step.get('summary', '')}")


@jobs_group.command("cancel")
@click.argument("job_id", type=str)
@click.pass_context
def cancel_cmd(ctx: click.Context, job_id: str) -> None:
    """Cancel a running or queued job."""
    from kronos_fincept.api.routes.jobs import cancel_job

    output_format = ctx.obj.get("output_format", "json")
    response = asyncio.run(cancel_job(job_id))
    payload = response.model_dump() if hasattr(response, "model_dump") else response.dict()

    if output_format == "json":
        output_json(payload)
    else:
        status = payload.get("status", "unknown")
        if status == "cancelled":
            click.echo(f"Job cancelled: {job_id}")
        else:
            click.echo(f"Job {job_id} status: {status} (not cancellable)")
