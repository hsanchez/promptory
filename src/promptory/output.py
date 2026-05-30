"""CLI output rendering helpers."""

from __future__ import annotations

import json
from enum import StrEnum

from rich.console import Console

from promptory.diff import (
  FileDiffSummary,
  PromptDiffSummary,
  YamlValueChange,
  is_missing_yaml_value,
)
from promptory.evidence import EvidenceChange, EvidenceComparison, EvidenceSummary
from promptory.gates import GateResult
from promptory.manager import VersionSummary
from promptory.metadata import IntegrityResult


class OutputFormat(StrEnum):
  """Supported structured CLI output formats."""

  TEXT = "text"
  JSON = "json"
  MARKDOWN = "markdown"
  GITHUB = "github"


def print_gate_result(console: Console, result: GateResult, output_format: OutputFormat) -> None:
  if output_format is OutputFormat.JSON:
    _print_json(console, _gate_result_to_dict(result))
    return
  if output_format is OutputFormat.GITHUB:
    _print_gate_result_github(console, result)
    return

  if not result.checks:
    console.print("[green]No release gates configured.[/green]")
    return
  for check in result.checks:
    if check.passed:
      console.print(f"[green]PASS[/green] {check.name}")
    else:
      console.print(f"[red]FAIL[/red] {check.name}: {check.reason}")


def print_integrity_result(console: Console, result: IntegrityResult) -> None:
  if result.passed:
    console.print(f"[green]Release integrity verified for {result.version}.[/green]")
    return
  console.print(f"[red]Release integrity failed for {result.version}.[/red]")
  for issue in result.issues:
    console.print(f"[red]FAIL[/red] {issue.file_name}: {issue.reason}")


def format_version_summary(summary: VersionSummary) -> str:
  evidence = f"{summary.evidence_count}"
  if summary.revoked_evidence_count:
    evidence = f"{evidence} ({summary.revoked_evidence_count} revoked)"
  return (
    f"{summary.version}  {summary.state.value}  gates: {summary.gate_status}  evidence: {evidence}"
  )


def print_evidence_list(
  console: Console,
  version: str,
  summaries: list[EvidenceSummary],
  output_format: OutputFormat,
) -> None:
  if output_format is OutputFormat.JSON:
    _print_json(
      console,
      {
        "version": version,
        "evidence": [_evidence_summary_to_dict(summary) for summary in summaries],
      },
    )
    return
  if output_format is OutputFormat.MARKDOWN:
    _print_evidence_list_markdown(console, version, summaries)
    return

  if not summaries:
    console.print("[yellow]No evidence found.[/yellow]")
    return
  for summary in summaries:
    state = "revoked" if summary.revoked else summary.status
    console.print(f"{summary.name}\t{summary.kind}\t{state}")


def print_evidence_comparison(
  console: Console,
  comparison: EvidenceComparison,
  output_format: OutputFormat,
) -> None:
  if output_format is OutputFormat.JSON:
    _print_json(console, _evidence_comparison_to_dict(comparison))
    return
  if output_format is OutputFormat.MARKDOWN:
    _print_evidence_comparison_markdown(console, comparison)
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


def print_diff_summary(
  console: Console,
  summary: PromptDiffSummary,
  output_format: OutputFormat,
) -> None:
  if output_format is OutputFormat.JSON:
    _print_json(console, _diff_summary_to_dict(summary))
    return
  if output_format is OutputFormat.MARKDOWN:
    _print_diff_summary_markdown(console, summary)
    return

  if not summary.files:
    console.print("[green]No prompt changes.[/green]")
    return

  console.print(f"Prompt diff summary: {summary.before_label} -> {summary.after_label}")
  for file_summary in summary.files:
    console.print("")
    _print_file_diff_summary(console, file_summary)


def _print_gate_result_github(console: Console, result: GateResult) -> None:
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


def _print_evidence_list_markdown(
  console: Console, version: str, summaries: list[EvidenceSummary]
) -> None:
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


def _print_evidence_comparison_markdown(console: Console, comparison: EvidenceComparison) -> None:
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


def _print_diff_summary_markdown(console: Console, summary: PromptDiffSummary) -> None:
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


def _print_file_diff_summary(console: Console, summary: FileDiffSummary) -> None:
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


def _print_json(console: Console, payload: dict[str, object]) -> None:
  console.print(json.dumps(payload, indent=2))


def _markdown_cell(value: object) -> str:
  return str(value).replace("|", "\\|").replace("\n", "<br>")


def _github_escape(value: str) -> str:
  return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
