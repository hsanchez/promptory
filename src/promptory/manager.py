"""High-level Promptory manager."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from promptory.config import PromptSpec, default_spec, load_spec
from promptory.diff import diff_current_against_drafts
from promptory.errors import PromptReleaseError
from promptory.gates import GateResult, check_release_gates, require_release_gates
from promptory.lint import lint_prompts
from promptory.release import (
  BumpType,
  create_release,
  promote_release,
  read_current_version,
  write_current_pointer,
)
from promptory.render import template_name_for


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
    current_dir = spec.versions_dir / current_version
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

  def diff(self) -> str:
    """Diff current prompts against rendered drafts."""
    return diff_current_against_drafts(self.spec())

  def rollback(self, version: str) -> None:
    """Point current.json at an existing release."""
    write_current_pointer(self.spec(), version)
