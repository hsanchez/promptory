"""Promptory CLI."""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
from typing import Annotated, Any, cast

import typer
from rich.console import Console
from rich.syntax import Syntax

from promptory.errors import PromptGateError, PromptReleaseError, PromptRenderError
from promptory.evidence import (
  add_evidence,
  compare_evidence,
  list_evidence,
  revoke_evidence,
  show_evidence,
)
from promptory.manager import PromptManager
from promptory.output import (
  OutputFormat,
  format_version_summary,
  print_diff_summary,
  print_evidence_comparison,
  print_evidence_list,
  print_gate_result,
  print_integrity_result,
)

app = typer.Typer(no_args_is_help=True)
evidence_app = typer.Typer(no_args_is_help=True)
app.add_typer(evidence_app, name="evidence")
console = Console()


OutputFormatOption = Annotated[OutputFormat, typer.Option("--format")]


@app.command()
def init(prompts_dir: Path = Path("prompts")) -> None:
  """Initialize prompt directories."""
  PromptManager(prompts_dir).init()
  console.print("[green]Initialized Promptory prompt structure.[/green]")


@app.command()
def draft(prompts_dir: Path = Path("prompts")) -> None:
  """Create drafts from the current release."""
  PromptManager(prompts_dir).draft_from_current()
  console.print("[green]Drafts created from the current release.[/green]")


@app.command()
def check(prompts_dir: Path = Path("prompts")) -> None:
  """Validate prompt drafts."""
  errors = PromptManager(prompts_dir).check()
  if errors:
    for error in errors:
      console.print(f"[red]ERROR[/red] {error}")
    raise typer.Exit(code=1)
  console.print("[green]Prompt check passed.[/green]")


@app.command()
def release(
  prompts_dir: Path = Path("prompts"),
  patch: bool = False,
  minor: bool = False,
  major: bool = False,
  staged: bool = False,
) -> None:
  """Create a new immutable prompt release."""
  selected = [
    name
    for name, enabled in {
      "patch": patch,
      "minor": minor,
      "major": major,
    }.items()
    if enabled
  ]

  bump = selected[0] if selected else "patch"
  if len(selected) > 1:
    console.print("[red]Choose only one bump type.[/red]")
    raise typer.Exit(code=1)

  manager = PromptManager(prompts_dir)
  errors = manager.check()
  if errors:
    for error in errors:
      console.print(f"[red]ERROR[/red] {error}")
    raise typer.Exit(code=1)

  version = manager.release(bump=bump, staged=staged)
  if staged:
    console.print(f"[green]Created staged prompt release {version}.[/green]")
    return
  console.print(f"[green]Created prompt release {version}.[/green]")


@app.command()
def diff(
  prompts_dir: Path = Path("prompts"),
  summary: bool = False,
  from_version: str | None = typer.Option(None, "--from"),
  to_version: str | None = typer.Option(None, "--to"),
  output_format: OutputFormatOption = OutputFormat.TEXT,
) -> None:
  """Show a colored diff between the current release and rendered drafts."""
  if not summary and output_format is not OutputFormat.TEXT:
    console.print("[red]ERROR[/red] --format requires --summary.")
    raise typer.Exit(code=1)
  if output_format is OutputFormat.GITHUB:
    console.print("[red]ERROR[/red] prompt diff does not support --format github.")
    raise typer.Exit(code=1)

  if summary:
    try:
      output = PromptManager(prompts_dir).diff_summary(
        before_version=from_version,
        after_version=to_version,
      )
    except (PromptReleaseError, PromptRenderError) as exc:
      console.print(f"[red]ERROR[/red] {exc}")
      raise typer.Exit(code=1) from None
    print_diff_summary(console, output, output_format)
    return
  if from_version is not None or to_version is not None:
    console.print("[red]ERROR[/red] --from and --to require --summary.")
    raise typer.Exit(code=1)

  output = PromptManager(prompts_dir).diff()
  if not output:
    console.print("[green]No prompt changes.[/green]")
    return
  console.print(Syntax(output, "diff"))


@app.command()
def rollback(version: str, prompts_dir: Path = Path("prompts")) -> None:
  """Point current.json at an existing release."""
  PromptManager(prompts_dir).rollback(version)
  console.print(f"[green]Pointed current.json at {version}.[/green]")


@app.command()
def promote(
  version: str,
  prompts_dir: Path = Path("prompts"),
  require_gates: bool = False,
) -> None:
  """Promote a release and record the lifecycle event."""
  try:
    PromptManager(prompts_dir).promote(version, require_gates=require_gates)
  except PromptGateError as exc:
    console.print(f"[red]ERROR[/red] {exc}")
    raise typer.Exit(code=1) from None
  console.print(f"[green]Promoted {version}.[/green]")


@app.command()
def gate(
  version: str,
  prompts_dir: Path = Path("prompts"),
  output_format: OutputFormatOption = OutputFormat.TEXT,
) -> None:
  """Check release gates for a version."""
  if output_format is OutputFormat.MARKDOWN:
    console.print("[red]ERROR[/red] prompt gate does not support --format markdown.")
    raise typer.Exit(code=1)

  try:
    result = PromptManager(prompts_dir).gate(version)
  except PromptGateError as exc:
    console.print(f"[red]ERROR[/red] {exc}")
    raise typer.Exit(code=1) from None
  print_gate_result(console, result, output_format)
  if not result.passed:
    raise typer.Exit(code=1)


@app.command()
def verify(version: str, prompts_dir: Path = Path("prompts")) -> None:
  """Verify release artifact integrity."""
  try:
    result = PromptManager(prompts_dir).verify(version)
  except PromptReleaseError as exc:
    console.print(f"[red]ERROR[/red] {exc}")
    raise typer.Exit(code=1) from None
  print_integrity_result(console, result)
  if not result.passed:
    raise typer.Exit(code=1)


@app.command()
def versions(prompts_dir: Path = Path("prompts")) -> None:
  """List available prompt releases."""
  try:
    summaries = PromptManager(prompts_dir).version_summaries()
  except PromptReleaseError as exc:
    console.print(f"[red]ERROR[/red] {exc}")
    raise typer.Exit(code=1) from None
  if not summaries:
    console.print("[yellow]No releases found.[/yellow]")
    return
  for summary in summaries:
    console.print(format_version_summary(summary))


@evidence_app.command("add")
def evidence_add(version: str, source_path: Path, prompts_dir: Path = Path("prompts")) -> None:
  """Attach immutable evidence to a release."""
  summary = add_evidence(PromptManager(prompts_dir).spec(), version, source_path)
  console.print(f"[green]Added evidence {summary.name} to {version}.[/green]")


@evidence_app.command("list")
def evidence_list(
  version: str,
  prompts_dir: Path = Path("prompts"),
  output_format: OutputFormatOption = OutputFormat.TEXT,
) -> None:
  """List evidence attached to a release."""
  if output_format is OutputFormat.GITHUB:
    console.print("[red]ERROR[/red] prompt evidence list does not support --format github.")
    raise typer.Exit(code=1)

  summaries = list_evidence(PromptManager(prompts_dir).spec(), version)
  print_evidence_list(console, version, summaries, output_format)


@evidence_app.command("show")
def evidence_show(version: str, name: str, prompts_dir: Path = Path("prompts")) -> None:
  """Show one evidence document."""
  evidence = show_evidence(PromptManager(prompts_dir).spec(), version, name)
  console.print(json.dumps(evidence, indent=2))


@evidence_app.command("compare")
def evidence_compare(
  before_version: str,
  after_version: str,
  prompts_dir: Path = Path("prompts"),
  output_format: OutputFormatOption = OutputFormat.TEXT,
) -> None:
  """Compare evidence between two releases."""
  if output_format is OutputFormat.GITHUB:
    console.print("[red]ERROR[/red] prompt evidence compare does not support --format github.")
    raise typer.Exit(code=1)

  comparison = compare_evidence(PromptManager(prompts_dir).spec(), before_version, after_version)
  print_evidence_comparison(console, comparison, output_format)


@evidence_app.command("revoke")
def evidence_revoke(
  version: str,
  name: str,
  reason: str = typer.Option(..., "--reason", help="Reason for revoking this evidence."),
  prompts_dir: Path = Path("prompts"),
) -> None:
  """Record revocation for existing evidence."""
  revoke_evidence(PromptManager(prompts_dir).spec(), version, name, reason)
  console.print(f"[green]Revoked evidence {name} for {version}.[/green]")


@app.command()
def serve(
  prompts_dir: Path = Path("prompts"),
  host: str = "0.0.0.0",
  port: int = 8000,
  reload: bool = False,
) -> None:
  """Start the prompt sidecar adapter."""
  try:
    uvicorn = cast(Any, importlib.import_module("uvicorn"))
    importlib.import_module("promptory.serve")
  except ImportError:
    console.print("[red]Sidecar adapter dependencies not found.[/red]")
    console.print("Install Promptory with the [bold]serve[/bold] extra.")
    raise typer.Exit(code=1) from None

  os.environ["PROMPTORY_PROMPTS_DIR"] = str(prompts_dir)

  console.print(f"[green]Starting prompt sidecar adapter on {host}:{port}[/green]")
  uvicorn.run("promptory.serve:app", host=host, port=port, reload=reload)


def main() -> None:
  """CLI entrypoint."""
  app()


if __name__ == "__main__":
  main()
