"""High-level Promptory manager."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

from promptory.config import PromptSpec, default_spec, load_spec
from promptory.diff import (
  PromptDiffSummary,
  diff_current_against_drafts,
  summarize_current_against_drafts,
  summarize_versions,
)
from promptory.errors import PromptEvidenceError, PromptGateError, PromptReleaseError
from promptory.evidence import list_evidence
from promptory.gates import GateResult, check_release_gates, require_release_gates
from promptory.lint import lint_prompts
from promptory.metadata import IntegrityResult
from promptory.release import (
  BumpType,
  create_release,
  list_versions,
  promote_release,
  read_current_version,
  verify_release,
  write_current_pointer,
)
from promptory.render import template_name_for


class VersionState(StrEnum):
  """Visible lifecycle state for a release version."""

  STAGED = "staged"
  CURRENT = "current"
  ARCHIVED = "archived"


@dataclass(frozen=True)
class VersionSummary:
  """CLI summary for one release version."""

  version: str
  state: VersionState
  gate_status: str
  evidence_count: int
  revoked_evidence_count: int


class PromptManager:
  """Manage prompt drafts and immutable prompt releases."""

  def __init__(self, prompts_dir: Path = Path("prompts")) -> None:
    self.prompts_dir = prompts_dir

  def init(self) -> None:
    """Initialize prompt directories and promptspec.yaml."""
    self.prompts_dir.mkdir(exist_ok=True)
    (self.prompts_dir / "drafts").mkdir(exist_ok=True)
    (self.prompts_dir / "versions").mkdir(exist_ok=True)

    spec_path = self.prompts_dir / "promptspec.yaml"
    if not spec_path.exists():
      spec_path.write_text(yaml.safe_dump(default_spec(), sort_keys=False))

    draft = self.prompts_dir / "drafts" / "system.yaml.j2"
    if not draft.exists():
      draft.write_text(
        "model: gpt-5.5\ntemperature: 0.2\nsystem_prompt: |\n  You are a helpful assistant.\n"
      )

  def spec(self) -> PromptSpec:
    """Load prompt spec."""
    return load_spec(self.prompts_dir)

  def draft_from_current(self) -> None:
    """Create drafts from the current release."""
    spec = self.spec()
    spec.drafts_dir.mkdir(parents=True, exist_ok=True)
    current_version = read_current_version(spec)
    if current_version is None:
      raise PromptReleaseError("No current release exists")
    current_dir = spec.release_dir(current_version)
    if not current_dir.is_dir():
      raise PromptReleaseError(f"Unknown release: {current_version}")

    for file_name in spec.files:
      current_path = current_dir / file_name
      draft_path = spec.drafts_dir / template_name_for(file_name)
      draft_path.parent.mkdir(parents=True, exist_ok=True)
      if current_path.exists():
        draft_path.write_text(current_path.read_text())
      elif not draft_path.exists():
        draft_path.write_text("")

  def check(self) -> list[str]:
    """Lint prompts."""
    return lint_prompts(self.spec())

  def release(
    self,
    bump: str | BumpType = BumpType.PATCH,
    variables: dict[str, Any] | None = None,
    staged: bool = False,
  ) -> str:
    """Create a release."""
    return create_release(self.spec(), bump=bump, variables=variables, staged=staged)

  def gate(self, version: str) -> GateResult:
    """Check release gates for a version."""
    return check_release_gates(self.spec(), version)

  def promote(self, version: str, require_gates: bool = False) -> None:
    """Promote a release and record the lifecycle event."""
    spec = self.spec()
    if require_gates:
      require_release_gates(spec, version)
    promote_release(spec, version)

  def verify(self, version: str) -> IntegrityResult:
    """Verify released prompt artifacts."""
    return verify_release(self.spec(), version)

  def version_summaries(self) -> list[VersionSummary]:
    """Summarize available release versions."""
    spec = self.spec()
    versions = list_versions(spec)
    current_version = read_current_version(spec)
    return [_version_summary(spec, version, current_version) for version in versions]

  def diff(self) -> str:
    """Diff current prompts against rendered drafts."""
    return diff_current_against_drafts(self.spec())

  def diff_summary(
    self,
    before_version: str | None = None,
    after_version: str | None = None,
  ) -> PromptDiffSummary:
    """Summarize prompt changes."""
    spec = self.spec()
    if before_version is None and after_version is None:
      return summarize_current_against_drafts(spec)
    if before_version is None or after_version is None:
      raise PromptReleaseError("Both --from and --to are required for version summary diffs")
    return summarize_versions(spec, before_version, after_version)

  def rollback(self, version: str) -> None:
    """Point current.json at an existing release."""
    write_current_pointer(self.spec(), version)


def _version_summary(spec: PromptSpec, version: str, current_version: str | None) -> VersionSummary:
  release_dir = spec.release_dir(version)
  evidence = list_evidence(spec, version)
  gate_status = _gate_status(spec, version)
  return VersionSummary(
    version=version,
    state=_version_state(release_dir, version, current_version),
    gate_status=gate_status,
    evidence_count=len(evidence),
    revoked_evidence_count=sum(1 for item in evidence if item.revoked),
  )


def _version_state(release_dir: Path, version: str, current_version: str | None) -> VersionState:
  if version == current_version:
    return VersionState.CURRENT
  events = _lifecycle_events(release_dir)
  if "release_staged" in events and "promoted" not in events:
    return VersionState.STAGED
  return VersionState.ARCHIVED


def _lifecycle_events(release_dir: Path) -> set[str]:
  lifecycle_path = release_dir / "lifecycle.jsonl"
  if not lifecycle_path.exists():
    return set()

  events: set[str] = set()
  for line in lifecycle_path.read_text().splitlines():
    if not line:
      continue
    try:
      event = json.loads(line)
    except json.JSONDecodeError as exc:
      raise PromptReleaseError(f"Invalid lifecycle event: {lifecycle_path}") from exc
    if isinstance(event, dict) and isinstance(event.get("event"), str):
      events.add(event["event"])
  return events


def _gate_status(spec: PromptSpec, version: str) -> str:
  if not spec.release_gates.evidence:
    return "n/a"
  try:
    result = check_release_gates(spec, version)
  except (PromptEvidenceError, PromptGateError):
    return "error"
  return "pass" if result.passed else "fail"
