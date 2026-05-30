import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from promptory.cli import app
from promptory.errors import PromptReleaseError
from promptory.manager import PromptManager


def test_verify_passes_for_unchanged_release(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  version = manager.release()

  result = manager.verify(version)

  assert result.passed is True
  assert result.version == version
  assert result.issues == ()


def test_verify_reports_modified_release_file(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  version = manager.release()
  (prompts_dir / "versions" / version / "system.yaml").write_text("model: edited\n")

  result = manager.verify(version)

  assert result.passed is False
  assert result.issues[0].file_name == "system.yaml"
  assert result.issues[0].reason == "checksum mismatch"


def test_verify_reports_missing_release_file(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  version = manager.release()
  (prompts_dir / "versions" / version / "system.yaml").unlink()

  result = manager.verify(version)

  assert result.passed is False
  assert result.issues[0].file_name == "system.yaml"
  assert result.issues[0].reason == "file missing"


def test_verify_reports_missing_checksum(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  version = manager.release()
  metadata_path = prompts_dir / "versions" / version / "metadata.json"
  metadata = json.loads(metadata_path.read_text())
  metadata["checksums"] = {}
  metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")

  result = manager.verify(version)

  assert result.passed is False
  assert result.issues[0].file_name == "system.yaml"
  assert result.issues[0].reason == "checksum missing"


def test_verify_reports_metadata_version_mismatch(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  version = manager.release()
  metadata_path = prompts_dir / "versions" / version / "metadata.json"
  metadata = json.loads(metadata_path.read_text())
  metadata["version"] = "v9.9.9"
  metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")

  result = manager.verify(version)

  assert result.passed is False
  assert result.version == version
  assert result.issues[0].file_name == "metadata.json"
  assert result.issues[0].reason == "version mismatch"


def test_verify_reports_empty_metadata_files(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  version = manager.release()
  metadata_path = prompts_dir / "versions" / version / "metadata.json"
  metadata = json.loads(metadata_path.read_text())
  metadata["files"] = []
  metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")

  result = manager.verify(version)

  assert result.passed is False
  assert result.issues[0].file_name == "metadata.json"
  assert result.issues[0].reason == "files list is empty"


def test_verify_rejects_malformed_metadata(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  version = manager.release()
  (prompts_dir / "versions" / version / "metadata.json").write_text("[]\n")

  with pytest.raises(PromptReleaseError, match="Release metadata must be an object"):
    manager.verify(version)


def test_verify_rejects_unsafe_metadata_file(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  version = manager.release()
  metadata_path = prompts_dir / "versions" / version / "metadata.json"
  metadata = json.loads(metadata_path.read_text())
  metadata["files"] = ["../system.yaml"]
  metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")

  with pytest.raises(PromptReleaseError, match="Release metadata file is invalid"):
    manager.verify(version)


def test_verify_rejects_unknown_release(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()

  with pytest.raises(PromptReleaseError, match="Unknown release: v9.9.9"):
    manager.verify("v9.9.9")


def test_verify_command_passes_for_unchanged_release(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  version = manager.release()
  runner = CliRunner()

  result = runner.invoke(app, ["verify", version, "--prompts-dir", str(prompts_dir)])

  assert result.exit_code == 0
  assert f"Release integrity verified for {version}." in result.output


def test_verify_command_fails_for_modified_release_file(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  version = manager.release()
  (prompts_dir / "versions" / version / "system.yaml").write_text("model: edited\n")
  runner = CliRunner()

  result = runner.invoke(app, ["verify", version, "--prompts-dir", str(prompts_dir)])

  assert result.exit_code == 1
  assert f"Release integrity failed for {version}." in result.output
  assert "FAIL system.yaml: checksum mismatch" in result.output
