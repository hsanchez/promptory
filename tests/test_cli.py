import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from promptory.cli import app
from promptory.manager import PromptManager


def write_cli_evidence(path: Path) -> None:
  path.write_text(
    json.dumps(
      {
        "kind": "eval",
        "name": "customer-support-regression",
        "status": "pass",
        "tool": "internal-eval-runner",
        "created_at": "2026-05-24T12:00:00Z",
      }
    )
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
