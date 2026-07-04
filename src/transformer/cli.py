"""CLI surface (architecture s11).

    python -m transformer.cli --inputs <file-or-dir ...> --config <config.json> [--out <path>]

--inputs accepts one or more files OR directories (repeat the flag);
detect.py routes each by type. If --out is omitted, JSON prints to stdout;
otherwise it is written there. Config-time (lane 1) errors exit non-zero with
a clear message, before any record is touched.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List, Optional

import typer

from .config import ConfigError, load_config
from .pipeline import DEFAULT_GITHUB_FIXTURES, run
from .project.interpreter import ProjectionError
from .project.validate import OutputValidationError

app = typer.Typer(add_completion=False, help=__doc__)


@app.command()
def main(
    inputs: List[Path] = typer.Option(
        ..., "--inputs", "-i", help="Input file(s) or directory(ies). Repeatable."
    ),
    config: Path = typer.Option(
        ..., "--config", "-c", help="Projection config JSON."
    ),
    out: Optional[Path] = typer.Option(
        None, "--out", "-o", help="Write JSON here; omit to print to stdout."
    ),
    github_fixtures: Path = typer.Option(
        DEFAULT_GITHUB_FIXTURES, "--github-fixtures",
        help="Directory of recorded GitHub fixtures (deterministic default)."
    ),
    live: bool = typer.Option(
        False, "--live",
        help="Opt-in: fetch GitHub from the live API instead of fixtures. "
             "NOT deterministic; never the default."
    ),
) -> None:
    # Lane 1: config-time validation. A bad config fails loudly, before any
    # record is read.
    try:
        cfg = load_config(config)
    except ConfigError as exc:
        typer.echo(f"config error: {exc}", err=True)
        raise typer.Exit(code=2)

    try:
        result = run(inputs, cfg, github_fixtures_dir=github_fixtures,
                     live_github=live)
    except (ProjectionError, OutputValidationError) as exc:
        typer.echo(f"projection error: {exc}", err=True)
        raise typer.Exit(code=1)

    payload = json.dumps(result.profiles, indent=2, ensure_ascii=False)

    if out is None:
        typer.echo(payload)
    else:
        Path(out).write_text(payload + "\n", encoding="utf-8")
        typer.echo(f"wrote {len(result.profiles)} profile(s) to {out}", err=True)

    for note in result.diagnostics:
        typer.echo(f"diagnostic: {note}", err=True)


if __name__ == "__main__":
    app()
