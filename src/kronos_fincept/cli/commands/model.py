"""kronos model -- Model utility commands."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import click


_CSV_FINETUNE_SCRIPTS = {
    "tokenizer": "finetune_csv/finetune_tokenizer.py",
    "predictor": "finetune_csv/finetune_base_model.py",
    "sequential": "finetune_csv/train_sequential.py",
}


@click.group("model")
def model_group() -> None:
    """Kronos model utilities."""


@model_group.command("finetune-csv")
@click.option("--config", "config_path", type=str, required=True, help="Path to a finetune_csv YAML config")
@click.option("--stage", type=click.Choice(sorted(_CSV_FINETUNE_SCRIPTS)), default="sequential", show_default=True)
@click.option("--kronos-repo", type=str, default=None, help="Upstream Kronos repo path")
@click.option("--execute", is_flag=True, default=False, help="Run the command; default only prints it")
def finetune_csv_cmd(config_path: str, stage: str, kronos_repo: str | None, execute: bool) -> None:
    """Wrap upstream Kronos finetune_csv scripts without copying them into KFL."""
    repo = Path(kronos_repo or os.environ.get("KRONOS_REPO_PATH") or _project_root() / "external" / "Kronos")
    script = repo / _CSV_FINETUNE_SCRIPTS[stage]
    config = Path(config_path)
    if not script.is_file():
        raise click.ClickException(f"upstream finetune script not found: {script}")
    if not config.is_file():
        raise click.ClickException(f"config file not found: {config}")

    command = [sys.executable, str(script), "--config", str(config)]
    if not execute:
        click.echo("Dry run. Re-run with --execute to start training.")
        click.echo(" ".join(command))
        return

    completed = subprocess.run(command, cwd=str(repo), check=False)
    if completed.returncode != 0:
        raise click.ClickException(f"finetune_csv exited with code {completed.returncode}")


def _project_root() -> Path:
    return Path(__file__).resolve().parents[4]
