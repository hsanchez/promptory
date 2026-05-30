import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from promptory.cli import app
from promptory.manager import PromptManager


def write_cli_evidence(
  path: Path,
  *,
  name: str = "customer-support-regression",
  status: str = "pass",
  pass_rate: float | None = None,
) -> None:
  document: dict[str, object] = {
    "kind": "eval",
    "name": name,
    "status": status,
    "tool": "internal-eval-runner",
    "created_at": "2026-05-24T12:00:00Z",
  }
  if pass_rate is not None:
    document["metrics"] = {"pass_rate": pass_rate}
  path.write_text(json.dumps(document))


def write_cli_gate_spec(prompts_dir: Path) -> None:
  (prompts_dir / "promptspec.yaml").write_text(
    "files:\n"
    "  - system.yaml\n"
    "required_variables: []\n"
    "max_file_bytes: 1000\n"
    "release_gates:\n"
    "  evidence:\n"
    "    - kind: eval\n"
    "      name: customer-support-regression\n"
    "      required_status: pass\n"
  )


@pytest.fixture
def staged_cli_release(tmp_path: Path) -> tuple[Path, Path]:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  manager.release(staged=True)
  evidence_path = tmp_path / "result.json"
  write_cli_evidence(evidence_path)
  return prompts_dir, evidence_path


def test_diff_command_reports_no_changes(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  manager.release()
  runner = CliRunner()

  result = runner.invoke(app, ["diff", "--prompts-dir", str(prompts_dir)])

  assert result.exit_code == 0
  assert result.output.strip() == "No prompt changes."


def test_diff_command_outputs_unified_diff(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  manager.release()
  (prompts_dir / "drafts" / "system.yaml.j2").write_text(
    "model: gpt-5.5\ntemperature: 0.1\nsystem_prompt: changed\n"
  )
  runner = CliRunner()

  result = runner.invoke(app, ["diff", "--prompts-dir", str(prompts_dir)])

  assert result.exit_code == 0
  assert "--- v0.0.1/system.yaml" in result.output
  assert "+++ drafts/system.yaml" in result.output
  assert "+system_prompt: changed" in result.output


def test_diff_summary_command_outputs_semantic_summary(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  manager.release()
  (prompts_dir / "drafts" / "system.yaml.j2").write_text(
    "model: gpt-5.5\ntemperature: 0.1\nsystem_prompt: changed\n"
  )
  runner = CliRunner()

  result = runner.invoke(app, ["diff", "--summary", "--prompts-dir", str(prompts_dir)])

  assert result.exit_code == 0
  assert "Prompt diff summary: v0.0.1 -> drafts" in result.output
  assert "system.yaml" in result.output
  assert "temperature: 0.2 -> 0.1" in result.output


def test_diff_summary_command_outputs_json(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  manager.release()
  (prompts_dir / "drafts" / "system.yaml.j2").write_text(
    "model: gpt-5.5\ntemperature: 0.1\nsystem_prompt: changed\n"
  )
  runner = CliRunner()

  result = runner.invoke(
    app,
    ["diff", "--summary", "--format", "json", "--prompts-dir", str(prompts_dir)],
  )

  payload = json.loads(result.output)
  assert result.exit_code == 0
  assert payload["before_label"] == "v0.0.1"
  assert payload["after_label"] == "drafts"
  assert payload["files"][0]["file_name"] == "system.yaml"
  assert payload["files"][0]["yaml_changes"][0]["path"] == "system_prompt"


def test_diff_summary_command_outputs_markdown(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  manager.release()
  (prompts_dir / "drafts" / "system.yaml.j2").write_text(
    "model: gpt-5.5\ntemperature: 0.1\nsystem_prompt: changed\n"
  )
  runner = CliRunner()

  result = runner.invoke(
    app,
    ["diff", "--summary", "--format", "markdown", "--prompts-dir", str(prompts_dir)],
  )

  assert result.exit_code == 0
  assert "## Prompt Diff Summary: v0.0.1 -> drafts" in result.output
  assert "| YAML path | Before | After |" in result.output


def test_diff_command_rejects_structured_format_without_summary(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  PromptManager(prompts_dir).init()
  runner = CliRunner()

  result = runner.invoke(app, ["diff", "--format", "json", "--prompts-dir", str(prompts_dir)])

  assert result.exit_code == 1
  assert "--format requires --summary" in result.output


def test_diff_summary_command_supports_version_comparison(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  first_version = manager.release()
  (prompts_dir / "drafts" / "system.yaml.j2").write_text(
    "model: gpt-5.5\ntemperature: 0.1\nsystem_prompt: changed\n"
  )
  second_version = manager.release()
  runner = CliRunner()

  result = runner.invoke(
    app,
    [
      "diff",
      "--summary",
      "--from",
      first_version,
      "--to",
      second_version,
      "--prompts-dir",
      str(prompts_dir),
    ],
  )

  assert result.exit_code == 0
  assert f"Prompt diff summary: {first_version} -> {second_version}" in result.output
  assert "system.yaml" in result.output


def test_diff_from_to_requires_summary(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  PromptManager(prompts_dir).init()
  runner = CliRunner()

  result = runner.invoke(
    app,
    ["diff", "--from", "v0.0.1", "--to", "v0.0.2", "--prompts-dir", str(prompts_dir)],
  )

  assert result.exit_code == 1
  assert "--from and --to require --summary" in result.output


def test_diff_summary_reports_unknown_version(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  first_version = manager.release()
  runner = CliRunner()

  result = runner.invoke(
    app,
    [
      "diff",
      "--summary",
      "--from",
      first_version,
      "--to",
      "v9.9.9",
      "--prompts-dir",
      str(prompts_dir),
    ],
  )

  assert result.exit_code == 1
  assert "Unknown release: v9.9.9" in result.output


def test_diff_summary_reports_render_errors(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  manager.release()
  (prompts_dir / "drafts" / "system.yaml.j2").write_text("model: {{ missing_model }}\n")
  runner = CliRunner()

  result = runner.invoke(app, ["diff", "--summary", "--prompts-dir", str(prompts_dir)])

  assert result.exit_code == 1
  assert "ERROR" in result.output
  assert "missing_model" in result.output


def test_versions_command_lists_available_versions(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  manager.release()
  manager.release()
  runner = CliRunner()

  result = runner.invoke(app, ["versions", "--prompts-dir", str(prompts_dir)])

  assert result.exit_code == 0
  assert result.output.splitlines() == ["v0.0.1", "v0.0.2"]


def test_versions_command_reports_when_no_releases_exist(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  PromptManager(prompts_dir).init()
  runner = CliRunner()

  result = runner.invoke(app, ["versions", "--prompts-dir", str(prompts_dir)])

  assert result.exit_code == 0
  assert result.output.strip() == "No releases found."


def test_release_command_creates_staged_release_without_current_pointer(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  PromptManager(prompts_dir).init()
  runner = CliRunner()

  result = runner.invoke(app, ["release", "--prompts-dir", str(prompts_dir), "--staged"])

  assert result.exit_code == 0
  assert "Created staged prompt release v0.0.1." in result.output
  assert (prompts_dir / "versions" / "v0.0.1" / "system.yaml").exists()
  assert not (prompts_dir / "current.json").exists()


def test_promote_command_updates_current_pointer(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  manager.release(staged=True)
  runner = CliRunner()

  result = runner.invoke(app, ["promote", "v0.0.1", "--prompts-dir", str(prompts_dir)])

  assert result.exit_code == 0
  assert "Promoted v0.0.1." in result.output
  assert json.loads((prompts_dir / "current.json").read_text())["version"] == "v0.0.1"


def test_gate_command_passes_with_valid_evidence(staged_cli_release: tuple[Path, Path]) -> None:
  prompts_dir, evidence_path = staged_cli_release
  write_cli_gate_spec(prompts_dir)
  runner = CliRunner()
  add_result = runner.invoke(
    app,
    [
      "evidence",
      "add",
      "v0.0.1",
      str(evidence_path),
      "--prompts-dir",
      str(prompts_dir),
    ],
  )
  assert add_result.exit_code == 0

  result = runner.invoke(app, ["gate", "v0.0.1", "--prompts-dir", str(prompts_dir)])

  assert result.exit_code == 0
  assert "PASS customer-support-regression" in result.output


def test_gate_command_outputs_json(staged_cli_release: tuple[Path, Path]) -> None:
  prompts_dir, evidence_path = staged_cli_release
  write_cli_gate_spec(prompts_dir)
  runner = CliRunner()
  add_result = runner.invoke(
    app,
    [
      "evidence",
      "add",
      "v0.0.1",
      str(evidence_path),
      "--prompts-dir",
      str(prompts_dir),
    ],
  )
  assert add_result.exit_code == 0

  result = runner.invoke(
    app,
    ["gate", "v0.0.1", "--format", "json", "--prompts-dir", str(prompts_dir)],
  )

  payload = json.loads(result.output)
  assert result.exit_code == 0
  assert payload["version"] == "v0.0.1"
  assert payload["passed"] is True
  assert payload["checks"][0]["name"] == "customer-support-regression"


def test_gate_command_fails_when_required_evidence_is_missing(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  write_cli_gate_spec(prompts_dir)
  manager.release(staged=True)
  runner = CliRunner()

  result = runner.invoke(app, ["gate", "v0.0.1", "--prompts-dir", str(prompts_dir)])

  assert result.exit_code == 1
  assert "FAIL customer-support-regression: required evidence missing" in result.output


def test_gate_command_outputs_github_annotation_for_failure(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  write_cli_gate_spec(prompts_dir)
  manager.release(staged=True)
  runner = CliRunner()

  result = runner.invoke(
    app,
    ["gate", "v0.0.1", "--format", "github", "--prompts-dir", str(prompts_dir)],
  )

  assert result.exit_code == 1
  assert "::error title=Promptory gate failed::customer-support-regression" in result.output


def test_gate_command_rejects_markdown_format(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  PromptManager(prompts_dir).init()
  runner = CliRunner()

  result = runner.invoke(
    app,
    ["gate", "v0.0.1", "--format", "markdown", "--prompts-dir", str(prompts_dir)],
  )

  assert result.exit_code == 1
  assert "prompt gate does not support --format markdown" in result.output


def test_promote_command_requires_passing_gates(staged_cli_release: tuple[Path, Path]) -> None:
  prompts_dir, evidence_path = staged_cli_release
  write_cli_gate_spec(prompts_dir)
  runner = CliRunner()
  add_result = runner.invoke(
    app,
    [
      "evidence",
      "add",
      "v0.0.1",
      str(evidence_path),
      "--prompts-dir",
      str(prompts_dir),
    ],
  )
  assert add_result.exit_code == 0

  result = runner.invoke(
    app,
    ["promote", "v0.0.1", "--require-gates", "--prompts-dir", str(prompts_dir)],
  )

  assert result.exit_code == 0
  assert json.loads((prompts_dir / "current.json").read_text())["version"] == "v0.0.1"


def test_promote_command_rejects_failing_gates(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  write_cli_gate_spec(prompts_dir)
  manager.release(staged=True)
  runner = CliRunner()

  result = runner.invoke(
    app,
    ["promote", "v0.0.1", "--require-gates", "--prompts-dir", str(prompts_dir)],
  )

  assert result.exit_code == 1
  assert "Release gates failed for v0.0.1" in result.output
  assert not (prompts_dir / "current.json").exists()


def test_evidence_add_command(staged_cli_release: tuple[Path, Path]) -> None:
  prompts_dir, evidence_path = staged_cli_release
  runner = CliRunner()

  result = runner.invoke(
    app,
    [
      "evidence",
      "add",
      "v0.0.1",
      str(evidence_path),
      "--prompts-dir",
      str(prompts_dir),
    ],
  )

  assert result.exit_code == 0
  assert "Added evidence customer-support-regression" in result.output


def test_evidence_list_command(staged_cli_release: tuple[Path, Path]) -> None:
  prompts_dir, evidence_path = staged_cli_release
  runner = CliRunner()
  add_result = runner.invoke(
    app,
    [
      "evidence",
      "add",
      "v0.0.1",
      str(evidence_path),
      "--prompts-dir",
      str(prompts_dir),
    ],
  )
  assert add_result.exit_code == 0

  result = runner.invoke(
    app,
    ["evidence", "list", "v0.0.1", "--prompts-dir", str(prompts_dir)],
  )

  assert result.exit_code == 0
  assert "customer-support-regression" in result.output


def test_evidence_list_command_outputs_json(staged_cli_release: tuple[Path, Path]) -> None:
  prompts_dir, evidence_path = staged_cli_release
  runner = CliRunner()
  add_result = runner.invoke(
    app,
    [
      "evidence",
      "add",
      "v0.0.1",
      str(evidence_path),
      "--prompts-dir",
      str(prompts_dir),
    ],
  )
  assert add_result.exit_code == 0

  result = runner.invoke(
    app,
    ["evidence", "list", "v0.0.1", "--format", "json", "--prompts-dir", str(prompts_dir)],
  )

  payload = json.loads(result.output)
  assert result.exit_code == 0
  assert payload["version"] == "v0.0.1"
  assert payload["evidence"][0]["name"] == "customer-support-regression"


def test_evidence_list_command_outputs_markdown(staged_cli_release: tuple[Path, Path]) -> None:
  prompts_dir, evidence_path = staged_cli_release
  runner = CliRunner()
  add_result = runner.invoke(
    app,
    [
      "evidence",
      "add",
      "v0.0.1",
      str(evidence_path),
      "--prompts-dir",
      str(prompts_dir),
    ],
  )
  assert add_result.exit_code == 0

  result = runner.invoke(
    app,
    [
      "evidence",
      "list",
      "v0.0.1",
      "--format",
      "markdown",
      "--prompts-dir",
      str(prompts_dir),
    ],
  )

  assert result.exit_code == 0
  assert "## Evidence for v0.0.1" in result.output
  assert "| Name | Kind | Status | Tool | Created |" in result.output


def test_evidence_show_command(staged_cli_release: tuple[Path, Path]) -> None:
  prompts_dir, evidence_path = staged_cli_release
  runner = CliRunner()
  add_result = runner.invoke(
    app,
    [
      "evidence",
      "add",
      "v0.0.1",
      str(evidence_path),
      "--prompts-dir",
      str(prompts_dir),
    ],
  )
  assert add_result.exit_code == 0

  result = runner.invoke(
    app,
    [
      "evidence",
      "show",
      "v0.0.1",
      "customer-support-regression",
      "--prompts-dir",
      str(prompts_dir),
    ],
  )

  assert result.exit_code == 0
  assert '"status": "pass"' in result.output


def test_evidence_compare_command_outputs_changes(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  first_version = manager.release(staged=True)
  second_version = manager.release(staged=True)
  before_path = tmp_path / "before.json"
  after_path = tmp_path / "after.json"
  write_cli_evidence(before_path, status="pass", pass_rate=0.91)
  write_cli_evidence(after_path, status="fail", pass_rate=0.94)
  runner = CliRunner()
  first_add = runner.invoke(
    app,
    [
      "evidence",
      "add",
      first_version,
      str(before_path),
      "--prompts-dir",
      str(prompts_dir),
    ],
  )
  second_add = runner.invoke(
    app,
    [
      "evidence",
      "add",
      second_version,
      str(after_path),
      "--prompts-dir",
      str(prompts_dir),
    ],
  )
  assert first_add.exit_code == 0
  assert second_add.exit_code == 0

  result = runner.invoke(
    app,
    ["evidence", "compare", first_version, second_version, "--prompts-dir", str(prompts_dir)],
  )

  assert result.exit_code == 0
  assert f"Evidence comparison: {first_version} -> {second_version}" in result.output
  assert "status: pass -> fail" in result.output
  assert "pass_rate: 0.91 -> 0.94" in result.output


def test_evidence_compare_command_outputs_json(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  first_version = manager.release(staged=True)
  second_version = manager.release(staged=True)
  before_path = tmp_path / "before.json"
  after_path = tmp_path / "after.json"
  write_cli_evidence(before_path, status="pass", pass_rate=0.91)
  write_cli_evidence(after_path, status="fail", pass_rate=0.94)
  runner = CliRunner()
  first_add = runner.invoke(
    app,
    [
      "evidence",
      "add",
      first_version,
      str(before_path),
      "--prompts-dir",
      str(prompts_dir),
    ],
  )
  second_add = runner.invoke(
    app,
    [
      "evidence",
      "add",
      second_version,
      str(after_path),
      "--prompts-dir",
      str(prompts_dir),
    ],
  )
  assert first_add.exit_code == 0
  assert second_add.exit_code == 0

  result = runner.invoke(
    app,
    [
      "evidence",
      "compare",
      first_version,
      second_version,
      "--format",
      "json",
      "--prompts-dir",
      str(prompts_dir),
    ],
  )

  payload = json.loads(result.output)
  assert result.exit_code == 0
  assert payload["before_version"] == first_version
  assert payload["after_version"] == second_version
  assert payload["changes"][0]["metrics"][0]["name"] == "pass_rate"


def test_evidence_compare_command_outputs_markdown(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  first_version = manager.release(staged=True)
  second_version = manager.release(staged=True)
  before_path = tmp_path / "before.json"
  after_path = tmp_path / "after.json"
  write_cli_evidence(before_path, status="pass", pass_rate=0.91)
  write_cli_evidence(after_path, status="fail", pass_rate=0.94)
  runner = CliRunner()
  first_add = runner.invoke(
    app,
    [
      "evidence",
      "add",
      first_version,
      str(before_path),
      "--prompts-dir",
      str(prompts_dir),
    ],
  )
  second_add = runner.invoke(
    app,
    [
      "evidence",
      "add",
      second_version,
      str(after_path),
      "--prompts-dir",
      str(prompts_dir),
    ],
  )
  assert first_add.exit_code == 0
  assert second_add.exit_code == 0

  result = runner.invoke(
    app,
    [
      "evidence",
      "compare",
      first_version,
      second_version,
      "--format",
      "markdown",
      "--prompts-dir",
      str(prompts_dir),
    ],
  )

  assert result.exit_code == 0
  assert f"## Evidence Comparison: {first_version} -> {second_version}" in result.output
  assert "| Field | Before | After |" in result.output


def test_evidence_compare_command_reports_no_changes(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  first_version = manager.release(staged=True)
  second_version = manager.release(staged=True)
  before_path = tmp_path / "before.json"
  after_path = tmp_path / "after.json"
  write_cli_evidence(before_path)
  write_cli_evidence(after_path)
  runner = CliRunner()
  first_add = runner.invoke(
    app,
    [
      "evidence",
      "add",
      first_version,
      str(before_path),
      "--prompts-dir",
      str(prompts_dir),
    ],
  )
  second_add = runner.invoke(
    app,
    [
      "evidence",
      "add",
      second_version,
      str(after_path),
      "--prompts-dir",
      str(prompts_dir),
    ],
  )
  assert first_add.exit_code == 0
  assert second_add.exit_code == 0

  result = runner.invoke(
    app,
    ["evidence", "compare", first_version, second_version, "--prompts-dir", str(prompts_dir)],
  )

  assert result.exit_code == 0
  assert result.output.strip() == "No evidence changes."


def test_evidence_revoke_command(staged_cli_release: tuple[Path, Path]) -> None:
  prompts_dir, evidence_path = staged_cli_release
  runner = CliRunner()
  add_result = runner.invoke(
    app,
    [
      "evidence",
      "add",
      "v0.0.1",
      str(evidence_path),
      "--prompts-dir",
      str(prompts_dir),
    ],
  )
  assert add_result.exit_code == 0

  result = runner.invoke(
    app,
    [
      "evidence",
      "revoke",
      "v0.0.1",
      "customer-support-regression",
      "--reason",
      "Fixture set was stale.",
      "--prompts-dir",
      str(prompts_dir),
    ],
  )

  assert result.exit_code == 0
  assert "Revoked evidence customer-support-regression" in result.output


def test_serve_command_uses_import_string_for_reload(
  tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
  calls: list[dict[str, object]] = []

  def run(app_target: str, host: str, port: int, reload: bool) -> None:
    calls.append(
      {
        "app_target": app_target,
        "host": host,
        "port": port,
        "reload": reload,
      }
    )

  def import_module(name: str) -> object:
    if name == "uvicorn":
      return SimpleNamespace(run=run)
    if name == "promptory.serve":
      return SimpleNamespace()
    raise ImportError(name)

  monkeypatch.setattr(importlib, "import_module", import_module)
  runner = CliRunner()

  result = runner.invoke(
    app,
    [
      "serve",
      "--prompts-dir",
      str(tmp_path / "prompts"),
      "--host",
      "127.0.0.1",
      "--port",
      "9000",
      "--reload",
    ],
  )

  assert result.exit_code == 0
  assert calls == [
    {
      "app_target": "promptory.serve:app",
      "host": "127.0.0.1",
      "port": 9000,
      "reload": True,
    }
  ]
