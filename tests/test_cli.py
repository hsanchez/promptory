from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

import promptkit.cli as cli
from promptkit.cli import app
from promptkit.manager import PromptManager


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
    if name == "promptkit.serve":
      return SimpleNamespace()
    raise ImportError(name)

  monkeypatch.setattr(cli.importlib, "import_module", import_module)
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
      "app_target": "promptkit.serve:app",
      "host": "127.0.0.1",
      "port": 9000,
      "reload": True,
    }
  ]
