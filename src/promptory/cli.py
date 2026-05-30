"""Promptory CLI."""

from __future__ import annotations

import importlib
import json
import os
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, cast

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
  EvidenceSummary,
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


class OutputFormat(StrEnum):
  """Supported structured CLI output formats."""

  TEXT = "text"
  JSON = "json"
  MARKDOWN = "markdown"
  GITHUB = "github"


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
    _print_diff_summary(output, output_format)
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
  _print_gate_result(result, output_format)
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
  _print_evidence_list(version, summaries, output_format)


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
  _print_evidence_comparison(comparison, output_format)


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


def _print_gate_result(result: GateResult, output_format: OutputFormat) -> None:
  if output_format is OutputFormat.JSON:
    _print_json(_gate_result_to_dict(result))
    return
  if output_format is OutputFormat.GITHUB:
    _print_gate_result_github(result)
    return

  if not result.checks:
    console.print("[green]No release gates configured.[/green]")
    return
  for check in result.checks:
    if check.passed:
      console.print(f"[green]PASS[/green] {check.name}")
    else:
      console.print(f"[red]FAIL[/red] {check.name}: {check.reason}")


def _print_gate_result_github(result: GateResult) -> None:
  if not result.checks:
    console.print(
      f"::notice title=Promptory gates::No release gates configured for {result.version}"
    )
    return
  if result.passed:
    console.print(
      f"::notice title=Promptory gates passed::{result.version} satisfies release gates"
    )
    return
  for check in result.checks:
    if not check.passed:
      message = f"{check.name}: {check.reason or 'release gate failed'}"
      console.print(f"::error title=Promptory gate failed::{_github_escape(message)}")


def _print_evidence_list(
  version: str,
  summaries: list[EvidenceSummary],
  output_format: OutputFormat,
) -> None:
  if output_format is OutputFormat.JSON:
    _print_json(
      {
        "version": version,
        "evidence": [_evidence_summary_to_dict(summary) for summary in summaries],
      }
    )
    return
  if output_format is OutputFormat.MARKDOWN:
    _print_evidence_list_markdown(version, summaries)
    return

  if not summaries:
    console.print("[yellow]No evidence found.[/yellow]")
    return
  for summary in summaries:
    state = "revoked" if summary.revoked else summary.status
    console.print(f"{summary.name}\t{summary.kind}\t{state}")


def _print_evidence_list_markdown(version: str, summaries: list[EvidenceSummary]) -> None:
  console.print(f"## Evidence for {version}")
  console.print("")
  if not summaries:
    console.print("No evidence found.")
    return
  console.print("| Name | Kind | Status | Tool | Created |")
  console.print("| --- | --- | --- | --- | --- |")
  for summary in summaries:
    state = "revoked" if summary.revoked else summary.status
    console.print(
      "| "
      f"{_markdown_cell(summary.name)} | "
      f"{_markdown_cell(summary.kind)} | "
      f"{_markdown_cell(state)} | "
      f"{_markdown_cell(summary.tool)} | "
      f"{_markdown_cell(summary.created_at)} |"
    )


def _print_evidence_comparison(
  comparison: EvidenceComparison,
  output_format: OutputFormat,
) -> None:
  if output_format is OutputFormat.JSON:
    _print_json(_evidence_comparison_to_dict(comparison))
    return
  if output_format is OutputFormat.MARKDOWN:
    _print_evidence_comparison_markdown(comparison)
    return

  if not comparison.changes:
    console.print("[green]No evidence changes.[/green]")
    return

  console.print(f"Evidence comparison: {comparison.before_version} -> {comparison.after_version}")
  for change in comparison.changes:
    console.print("")
    console.print(change.name)
    for line in _evidence_change_lines(change):
      console.print(f"  {line}")


def _print_evidence_comparison_markdown(comparison: EvidenceComparison) -> None:
  console.print(
    f"## Evidence Comparison: {comparison.before_version} -> {comparison.after_version}"
  )
  console.print("")
  if not comparison.changes:
    console.print("No evidence changes.")
    return
  for change in comparison.changes:
    console.print(f"### {change.name}")
    console.print("")
    console.print("| Field | Before | After |")
    console.print("| --- | --- | --- |")
    for line in _evidence_change_lines(change):
      field, values = line.split(": ", 1)
      before, after = values.split(" -> ", 1)
      console.print(
        f"| {_markdown_cell(field)} | {_markdown_cell(before)} | {_markdown_cell(after)} |"
      )
    console.print("")


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


def _print_diff_summary(summary: PromptDiffSummary, output_format: OutputFormat) -> None:
  if output_format is OutputFormat.JSON:
    _print_json(_diff_summary_to_dict(summary))
    return
  if output_format is OutputFormat.MARKDOWN:
    _print_diff_summary_markdown(summary)
    return

  if not summary.files:
    console.print("[green]No prompt changes.[/green]")
    return

  console.print(f"Prompt diff summary: {summary.before_label} -> {summary.after_label}")
  for file_summary in summary.files:
    console.print("")
    _print_file_diff_summary(file_summary)


def _print_diff_summary_markdown(summary: PromptDiffSummary) -> None:
  console.print(f"## Prompt Diff Summary: {summary.before_label} -> {summary.after_label}")
  console.print("")
  if not summary.files:
    console.print("No prompt changes.")
    return
  for file_summary in summary.files:
    delta = file_summary.after_chars - file_summary.before_chars
    sign = "+" if delta >= 0 else ""
    console.print(f"### {file_summary.file_name}")
    console.print("")
    console.print(
      f"- chars: {file_summary.before_chars} -> {file_summary.after_chars} ({sign}{delta})"
    )
    if file_summary.yaml_changes:
      console.print("")
      console.print("| YAML path | Before | After |")
      console.print("| --- | --- | --- |")
      for change in file_summary.yaml_changes:
        console.print(
          "| "
          f"{_markdown_cell(change.path)} | "
          f"{_markdown_cell(_format_yaml_value(change.before))} | "
          f"{_markdown_cell(_format_yaml_value(change.after))} |"
        )
    console.print("")


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


def _gate_result_to_dict(result: GateResult) -> dict[str, object]:
  return {
    "version": result.version,
    "passed": result.passed,
    "checks": [
      {
        "kind": check.kind,
        "name": check.name,
        "required_status": check.required_status,
        "status": check.status,
        "passed": check.passed,
        "reason": check.reason,
      }
      for check in result.checks
    ],
  }


def _evidence_summary_to_dict(summary: EvidenceSummary) -> dict[str, object]:
  return {
    "name": summary.name,
    "kind": summary.kind,
    "status": summary.status,
    "tool": summary.tool,
    "created_at": summary.created_at,
    "summary": summary.summary,
    "revoked": summary.revoked,
    "revocation_reason": summary.revocation_reason,
  }


def _evidence_comparison_to_dict(comparison: EvidenceComparison) -> dict[str, object]:
  return {
    "before_version": comparison.before_version,
    "after_version": comparison.after_version,
    "changes": [
      {
        "kind": change.kind,
        "name": change.name,
        "before_status": change.before_status,
        "after_status": change.after_status,
        "before_revoked": change.before_revoked,
        "after_revoked": change.after_revoked,
        "metrics": [
          {
            "name": metric.name,
            "before": metric.before,
            "after": metric.after,
          }
          for metric in change.metrics
        ],
      }
      for change in comparison.changes
    ],
  }


def _diff_summary_to_dict(summary: PromptDiffSummary) -> dict[str, object]:
  return {
    "before_label": summary.before_label,
    "after_label": summary.after_label,
    "files": [
      {
        "file_name": file_summary.file_name,
        "before_chars": file_summary.before_chars,
        "after_chars": file_summary.after_chars,
        "char_delta": file_summary.after_chars - file_summary.before_chars,
        "yaml_changes": [_yaml_change_to_dict(change) for change in file_summary.yaml_changes],
      }
      for file_summary in summary.files
    ],
  }


def _yaml_change_to_dict(change: YamlValueChange) -> dict[str, object]:
  return {
    "path": change.path,
    "before": None if is_missing_yaml_value(change.before) else change.before,
    "after": None if is_missing_yaml_value(change.after) else change.after,
    "before_missing": is_missing_yaml_value(change.before),
    "after_missing": is_missing_yaml_value(change.after),
  }


def _print_json(payload: dict[str, object]) -> None:
  console.print(json.dumps(payload, indent=2))


def _markdown_cell(value: object) -> str:
  return str(value).replace("|", "\\|").replace("\n", "<br>")


def _github_escape(value: str) -> str:
  return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


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
