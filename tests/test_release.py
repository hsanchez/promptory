import json
from pathlib import Path

import pytest

from promptkit.config import PromptSpec
from promptkit.errors import PromptReleaseError
from promptkit.manager import PromptManager
from promptkit.release import (
  BumpType,
  bump_version,
  create_release,
  normalize_version,
  parse_bump_type,
  parse_version,
  read_current_version,
)


def make_spec(prompts_dir: Path) -> PromptSpec:
  return PromptSpec(
    prompts_dir=prompts_dir,
    files=("system.yaml",),
    required_variables=[],
    max_file_bytes=1000,
  )


def test_parse_version_accepts_prefixed_and_unprefixed_versions() -> None:
  assert parse_version("v1.2.3") == (1, 2, 3)
  assert parse_version("1.2.3") == (1, 2, 3)
  assert normalize_version("1.2.3") == "v1.2.3"


def test_parse_version_rejects_invalid_version() -> None:
  with pytest.raises(PromptReleaseError):
    parse_version("../v1.2.3")


@pytest.mark.parametrize(
  ("current", "bump", "expected"),
  [
    (None, BumpType.PATCH, "v0.0.1"),
    ("v1.2.3", BumpType.PATCH, "v1.2.4"),
    ("v1.2.3", BumpType.MINOR, "v1.3.0"),
    ("v1.2.3", BumpType.MAJOR, "v2.0.0"),
  ],
)
def test_bump_version(current: str | None, bump: BumpType, expected: str) -> None:
  assert bump_version(current, bump) == expected


def test_parse_bump_type_rejects_unknown_bump() -> None:
  with pytest.raises(PromptReleaseError):
    parse_bump_type("tiny")


def test_create_release_writes_visible_version_metadata_and_pointer(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()

  version = create_release(manager.spec())

  release_dir = prompts_dir / "versions" / version
  metadata = json.loads((release_dir / "metadata.json").read_text())
  pointer = json.loads((prompts_dir / "current.json").read_text())
  assert version == "v0.0.1"
  assert (release_dir / "system.yaml").exists()
  assert metadata["version"] == version
  assert metadata["files"] == ["system.yaml"]
  assert "system.yaml" in metadata["checksums"]
  assert pointer["version"] == version


def test_create_release_accepts_explicit_variables(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  drafts_dir = prompts_dir / "drafts"
  drafts_dir.mkdir(parents=True)
  (drafts_dir / "system.yaml.j2").write_text("model: gpt-5.5\nsystem_prompt: {{ system_prompt }}\n")

  version = create_release(
    make_spec(prompts_dir),
    variables={"system_prompt": "Be precise."},
  )

  release = prompts_dir / "versions" / version / "system.yaml"
  assert "Be precise." in release.read_text()


def test_read_current_version_rejects_malformed_pointer(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  prompts_dir.mkdir()
  (prompts_dir / "current.json").write_text("[]\n")

  with pytest.raises(PromptReleaseError):
    read_current_version(make_spec(prompts_dir))
