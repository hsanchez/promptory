"""Prompt diff helpers."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import unified_diff
from pathlib import Path
from typing import Any

import yaml

from promptory.config import PromptSpec
from promptory.errors import PromptReleaseError
from promptory.release import normalize_version, read_current_version
from promptory.render import render_prompts

ScalarValue = str | int | float | bool | None


@dataclass(frozen=True)
class MissingYamlValue:
  """Marker for a YAML path missing from one side of a diff."""


YAML_MISSING = MissingYamlValue()
YamlComparableValue = ScalarValue | MissingYamlValue


@dataclass(frozen=True)
class YamlValueChange:
  """Scalar YAML value change."""

  path: str
  before: YamlComparableValue
  after: YamlComparableValue


@dataclass(frozen=True)
class FileDiffSummary:
  """Semantic diff summary for one managed prompt file."""

  file_name: str
  before_chars: int
  after_chars: int
  yaml_changes: tuple[YamlValueChange, ...]


@dataclass(frozen=True)
class PromptDiffSummary:
  """Semantic diff summary for prompt artifacts."""

  before_label: str
  after_label: str
  files: tuple[FileDiffSummary, ...]


def diff_lines(content: str) -> list[str]:
  """Return lines safe for unified_diff output."""
  lines = content.splitlines(keepends=True)
  if lines and not lines[-1].endswith("\n"):
    lines[-1] = f"{lines[-1]}\n"
  return lines


def diff_current_against_drafts(spec: PromptSpec) -> str:
  """Return a unified diff between the current release and rendered drafts."""
  rendered = render_prompts(spec)
  chunks: list[str] = []
  current_version = read_current_version(spec)
  current_dir = spec.release_dir(current_version) if current_version else None

  for file_name, draft_content in rendered.items():
    current_path = current_dir / file_name if current_dir is not None else None
    current_content = (
      current_path.read_text() if current_path is not None and current_path.exists() else ""
    )

    chunks.extend(
      unified_diff(
        diff_lines(current_content),
        diff_lines(draft_content),
        fromfile=f"{current_version or 'current'}/{file_name}",
        tofile=f"drafts/{file_name}",
      )
    )

  return "".join(chunks)


def summarize_current_against_drafts(spec: PromptSpec) -> PromptDiffSummary:
  """Return a semantic summary between the current release and rendered drafts."""
  rendered = render_prompts(spec)
  current_version = read_current_version(spec)
  current_dir = spec.release_dir(current_version) if current_version else None
  files: list[FileDiffSummary] = []

  for file_name, draft_content in rendered.items():
    current_path = current_dir / file_name if current_dir is not None else None
    current_content = (
      current_path.read_text() if current_path is not None and current_path.exists() else ""
    )
    summary = summarize_file(file_name, current_content, draft_content)
    if summary is not None:
      files.append(summary)

  return PromptDiffSummary(
    before_label=current_version or "current",
    after_label="drafts",
    files=tuple(files),
  )


def summarize_versions(
  spec: PromptSpec, before_version: str, after_version: str
) -> PromptDiffSummary:
  """Return a semantic summary between two released versions."""
  before = normalize_version(before_version)
  after = normalize_version(after_version)
  before_dir = spec.release_dir(before)
  after_dir = spec.release_dir(after)
  if not before_dir.is_dir():
    raise PromptReleaseError(f"Unknown release: {before}")
  if not after_dir.is_dir():
    raise PromptReleaseError(f"Unknown release: {after}")

  files: list[FileDiffSummary] = []
  for file_name in sorted(_release_yaml_files(before_dir) | _release_yaml_files(after_dir)):
    before_content = _read_release_file(before_dir, file_name)
    after_content = _read_release_file(after_dir, file_name)
    summary = summarize_file(file_name, before_content, after_content)
    if summary is not None:
      files.append(summary)

  return PromptDiffSummary(before_label=before, after_label=after, files=tuple(files))


def summarize_file(
  file_name: str, before_content: str, after_content: str
) -> FileDiffSummary | None:
  """Return semantic summary for changed file content."""
  if before_content == after_content:
    return None
  return FileDiffSummary(
    file_name=file_name,
    before_chars=len(before_content),
    after_chars=len(after_content),
    yaml_changes=_yaml_value_changes(before_content, after_content),
  )


def _read_release_file(version_dir: Path, file_name: str) -> str:
  path = version_dir / file_name
  return path.read_text() if path.exists() else ""


def _release_yaml_files(version_dir: Path) -> set[str]:
  return {
    path.relative_to(version_dir).as_posix()
    for path in version_dir.rglob("*.yaml")
    if path.is_file()
  }


def _yaml_value_changes(before_content: str, after_content: str) -> tuple[YamlValueChange, ...]:
  before_values = _flatten_scalar_yaml(before_content)
  after_values = _flatten_scalar_yaml(after_content)
  changes: list[YamlValueChange] = []
  for path in sorted(before_values.keys() | after_values.keys()):
    before = before_values.get(path, YAML_MISSING)
    after = after_values.get(path, YAML_MISSING)
    if before != after:
      changes.append(YamlValueChange(path=path, before=before, after=after))
  return tuple(changes)


def _flatten_scalar_yaml(content: str) -> dict[str, ScalarValue]:
  try:
    loaded = yaml.safe_load(content) if content else {}
  except yaml.YAMLError:
    return {}
  flattened: dict[str, ScalarValue] = {}
  _flatten_scalar_value(loaded, "", flattened)
  return flattened


def _flatten_scalar_value(value: Any, prefix: str, flattened: dict[str, ScalarValue]) -> None:
  if isinstance(value, dict):
    for key, child in value.items():
      if not isinstance(key, str):
        continue
      path = f"{prefix}.{key}" if prefix else key
      _flatten_scalar_value(child, path, flattened)
    return
  if isinstance(value, list):
    flattened[prefix] = repr(value)
    return
  if value is None or isinstance(value, str | int | float | bool):
    flattened[prefix] = value


def is_missing_yaml_value(value: object) -> bool:
  """Return whether a summary value represents an absent YAML path."""
  return value is YAML_MISSING
