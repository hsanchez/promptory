import json
from pathlib import Path

import pytest

from promptory.errors import PromptReleaseError
from promptory.manager import PromptManager


def test_init_creates_drafts_versions_and_default_spec(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)

  manager.init()

  assert (prompts_dir / "drafts" / "system.yaml.j2").exists()
  assert (prompts_dir / "versions").is_dir()
  assert (prompts_dir / "promptspec.yaml").exists()
  assert not (prompts_dir / ".vault").exists()
  assert not (prompts_dir / "current").exists()


def test_diff_has_changes_against_current_pointer(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)

  manager.init()
  manager.release()

  draft = prompts_dir / "drafts" / "system.yaml.j2"
  draft.write_text(
    "model: gpt-5.5\ntemperature: 0.1\nsystem_prompt: |\n  You are a careful verifier.\n"
  )

  diff = manager.diff()

  assert "v0.0.1/system.yaml" in diff
  assert "careful verifier" in diff


def test_diff_separates_multiple_files_without_trailing_newlines(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)

  manager.init()
  manager.release()
  (prompts_dir / "promptspec.yaml").write_text(
    "files:\n"
    "  - system.yaml\n"
    "  - input_guardrail.yaml\n"
    "  - output_guardrail.yaml\n"
    "required_variables: []\n"
    "max_file_bytes: 1000\n"
  )
  (prompts_dir / "drafts" / "input_guardrail.yaml.j2").write_text("policy: first")
  (prompts_dir / "drafts" / "output_guardrail.yaml.j2").write_text("policy: second")

  diff = manager.diff()

  assert "+policy: first\n--- v0.0.1/output_guardrail.yaml" in diff
  assert "first---" not in diff


def test_rollback_updates_current_pointer(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)

  manager.init()
  first_version = manager.release()
  draft = prompts_dir / "drafts" / "system.yaml.j2"
  draft.write_text(
    "model: gpt-5.5\ntemperature: 0.1\nsystem_prompt: |\n  You are a careful verifier.\n"
  )
  manager.release()

  manager.rollback(first_version)

  pointer = json.loads((prompts_dir / "current.json").read_text())
  assert pointer["version"] == first_version


def test_rollback_rejects_unknown_or_unsafe_version(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)

  manager.init()

  with pytest.raises(PromptReleaseError):
    manager.rollback("../v0.0.1")

  with pytest.raises(PromptReleaseError):
    manager.rollback("v9.9.9")


def test_draft_from_current_copies_current_release_to_drafts(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  manager.release()
  (prompts_dir / "drafts" / "system.yaml.j2").write_text("model: changed\n")

  manager.draft_from_current()

  assert (prompts_dir / "drafts" / "system.yaml.j2").read_text().startswith("model: gpt-5.5")


def test_draft_from_current_requires_current_pointer(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()

  with pytest.raises(PromptReleaseError):
    manager.draft_from_current()


def test_check_reports_template_variables_missing_from_spec(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  (prompts_dir / "drafts" / "system.yaml.j2").write_text(
    "model: gpt-5.5\nsystem_prompt: {{ system_prompt }}\n"
  )

  errors = manager.check()

  assert any("not listed in promptspec.yaml" in error for error in errors)
