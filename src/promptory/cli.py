"""Promptory CLI."""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
from typing import Any, cast

import typer
from rich.console import Console
from rich.syntax import Syntax

from promptory.diff import (
  FileDiffSummary,
  PromptDiffSummary,
  YamlValueChange,
  is_missing_yaml_value,
)
from promptory.errors import PromptGateError, PromptReleaseError, PromptRenderError
from promptory.evidence import (
  EvidenceChange,
  EvidenceComparison,
  add_evidence,
  compare_evidence,
  list_evidence,
  revoke_evidence,
  show_evidence,
)
from promptory.gates import GateResult
from promptory.manager import PromptManager
from promptory.store import PromptStore

app = typer.Typer(no_args_is_help=True)
evidence_app = typer.Typer(no_args_is_help=True)
app.add_typer(evidence_app, name="evidence")
console = Console()


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
) -> None:
  """Show a colored diff between the current release and rendered drafts."""
  if summary:
    try:
      output = PromptManager(prompts_dir).diff_summary(
        before_version=from_version,
        after_version=to_version,
      )
    except (PromptReleaseError, PromptRenderError) as exc:
      console.print(f"[red]ERROR[/red] {exc}")
      raise typer.Exit(code=1) from None
    _print_diff_summary(output)
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
def gate(version: str, prompts_dir: Path = Path("prompts")) -> None:
  """Check release gates for a version."""
  try:
    result = PromptManager(prompts_dir).gate(version)
  except PromptGateError as exc:
    console.print(f"[red]ERROR[/red] {exc}")
    raise typer.Exit(code=1) from None
  _print_gate_result(result)
  if not result.passed:
    raise typer.Exit(code=1)


@app.command()
def versions(prompts_dir: Path = Path("prompts")) -> None:
  """List available prompt releases."""
  available_versions = PromptStore(prompts_dir).list_versions()
  if not available_versions:
    console.print("[yellow]No releases found.[/yellow]")
    return
  for version in available_versions:
    console.print(version)


@evidence_app.command("add")
def evidence_add(version: str, source_path: Path, prompts_dir: Path = Path("prompts")) -> None:
  """Attach immutable evidence to a release."""
  summary = add_evidence(PromptManager(prompts_dir).spec(), version, source_path)
  console.print(f"[green]Added evidence {summary.name} to {version}.[/green]")


@evidence_app.command("list")
def evidence_list(version: str, prompts_dir: Path = Path("prompts")) -> None:
  """List evidence attached to a release."""
  summaries = list_evidence(PromptManager(prompts_dir).spec(), version)
  if not summaries:
    console.print("[yellow]No evidence found.[/yellow]")
    return
  for summary in summaries:
    state = "revoked" if summary.revoked else summary.status
    console.print(f"{summary.name}\t{summary.kind}\t{state}")


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
) -> None:
  """Compare evidence between two releases."""
  comparison = compare_evidence(PromptManager(prompts_dir).spec(), before_version, after_version)
  _print_evidence_comparison(comparison)


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


def _print_gate_result(result: GateResult) -> None:
  if not result.checks:
    console.print("[green]No release gates configured.[/green]")
    return
  for check in result.checks:
    if check.passed:
      console.print(f"[green]PASS[/green] {check.name}")
    else:
      console.print(f"[red]FAIL[/red] {check.name}: {check.reason}")


def _print_evidence_comparison(comparison: EvidenceComparison) -> None:
  if not comparison.changes:
    console.print("[green]No evidence changes.[/green]")
    return

  console.print(f"Evidence comparison: {comparison.before_version} -> {comparison.after_version}")
  for change in comparison.changes:
    console.print("")
    console.print(change.name)
    for line in _evidence_change_lines(change):
      console.print(f"  {line}")


def _evidence_change_lines(change: EvidenceChange) -> list[str]:
  lines: list[str] = []
  if change.before_status != change.after_status:
    lines.append(
      f"status: {_format_optional_value(change.before_status)} -> "
      f"{_format_optional_value(change.after_status)}"
    )
  if change.before_revoked != change.after_revoked:
    lines.append(
      f"revoked: {_format_optional_value(change.before_revoked)} -> "
      f"{_format_optional_value(change.after_revoked)}"
    )
  for metric in change.metrics:
    lines.append(
      f"{metric.name}: {_format_optional_value(metric.before)} -> "
      f"{_format_optional_value(metric.after)}"
    )
  return lines


def _format_optional_value(value: object | None) -> str:
  if value is None:
    return "missing"
  if isinstance(value, bool):
    return str(value).lower()
  return str(value)


def _print_diff_summary(summary: PromptDiffSummary) -> None:
  if not summary.files:
    console.print("[green]No prompt changes.[/green]")
    return

  console.print(f"Prompt diff summary: {summary.before_label} -> {summary.after_label}")
  for file_summary in summary.files:
    console.print("")
    _print_file_diff_summary(file_summary)


def _print_file_diff_summary(summary: FileDiffSummary) -> None:
  delta = summary.after_chars - summary.before_chars
  sign = "+" if delta >= 0 else ""
  console.print(summary.file_name)
  console.print(f"  chars: {summary.before_chars} -> {summary.after_chars} ({sign}{delta})")
  if not summary.yaml_changes:
    return
  console.print("  YAML values:")
  for change in summary.yaml_changes:
    console.print(f"    {change.path}: {_format_yaml_change_value(change)}")


def _format_yaml_change_value(change: YamlValueChange) -> str:
  return f"{_format_yaml_value(change.before)} -> {_format_yaml_value(change.after)}"


def _format_yaml_value(value: object) -> str:
  if is_missing_yaml_value(value):
    return "missing"
  if value is None:
    return "null"
  if isinstance(value, bool):
    return str(value).lower()
  return str(value)


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
