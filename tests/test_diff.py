from pathlib import Path

from promptory.diff import (
  is_missing_yaml_value,
  summarize_current_against_drafts,
  summarize_versions,
)
from promptory.manager import PromptManager


def test_summarize_current_against_drafts_reports_scalar_yaml_and_char_changes(
  tmp_path: Path,
) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  manager.release()
  (prompts_dir / "drafts" / "system.yaml.j2").write_text(
    "model: gpt-5.5\ntemperature: 0.1\nsystem_prompt: changed\n"
  )

  summary = summarize_current_against_drafts(manager.spec())

  assert summary.before_label == "v0.0.1"
  assert summary.after_label == "drafts"
  assert len(summary.files) == 1
  file_summary = summary.files[0]
  assert file_summary.file_name == "system.yaml"
  assert file_summary.before_chars != file_summary.after_chars
  assert [(change.path, change.before, change.after) for change in file_summary.yaml_changes] == [
    ("system_prompt", "You are a helpful assistant.", "changed"),
    ("temperature", 0.2, 0.1),
  ]


def test_summarize_versions_reports_release_to_release_changes(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  first_version = manager.release()
  (prompts_dir / "drafts" / "system.yaml.j2").write_text(
    "model: gpt-5.5\ntemperature: 0.1\nsystem_prompt: changed\n"
  )
  second_version = manager.release()

  summary = summarize_versions(manager.spec(), first_version, second_version)

  assert summary.before_label == first_version
  assert summary.after_label == second_version
  assert len(summary.files) == 1
  assert summary.files[0].file_name == "system.yaml"


def test_summarize_versions_omits_unchanged_files(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  first_version = manager.release()
  second_version = manager.release()

  summary = summarize_versions(manager.spec(), first_version, second_version)

  assert summary.files == ()


def test_summarize_file_distinguishes_null_from_missing(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  manager.release()
  (prompts_dir / "drafts" / "system.yaml.j2").write_text("foo: null\n")
  first_version = manager.release()
  (prompts_dir / "drafts" / "system.yaml.j2").write_text("{}\n")
  second_version = manager.release()

  summary = summarize_versions(manager.spec(), first_version, second_version)

  change = summary.files[0].yaml_changes[0]
  assert change.path == "foo"
  assert change.before is None
  assert is_missing_yaml_value(change.after)


def test_summarize_file_reports_list_changes(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  (prompts_dir / "drafts" / "system.yaml.j2").write_text(
    "model: gpt-5.5\nstop_sequences:\n  - one\n  - two\n"
  )
  first_version = manager.release()
  (prompts_dir / "drafts" / "system.yaml.j2").write_text(
    "model: gpt-5.5\nstop_sequences:\n  - one\n"
  )
  second_version = manager.release()

  summary = summarize_versions(manager.spec(), first_version, second_version)

  assert summary.files[0].yaml_changes[0].path == "stop_sequences"


def test_summarize_versions_includes_yaml_files_removed_from_current_spec(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  (prompts_dir / "promptspec.yaml").write_text(
    "files:\n  - system.yaml\n  - user.yaml\nrequired_variables: []\nmax_file_bytes: 1000\n"
  )
  (prompts_dir / "drafts" / "user.yaml.j2").write_text("message: hello\n")
  first_version = manager.release()
  (prompts_dir / "promptspec.yaml").write_text(
    "files:\n  - system.yaml\nrequired_variables: []\nmax_file_bytes: 1000\n"
  )
  second_version = manager.release()

  summary = summarize_versions(manager.spec(), first_version, second_version)

  assert "user.yaml" in {file_summary.file_name for file_summary in summary.files}
