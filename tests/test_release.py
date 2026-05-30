import json
from pathlib import Path

import pytest

import promptory.release as release_module
from promptory.config import PromptSpec, ReleaseGates
from promptory.errors import PromptReleaseError
from promptory.manager import PromptManager
from promptory.release import (
  BumpType,
  ReleaseVersion,
  bump_version,
  create_release,
  list_versions,
  normalize_version,
  parse_bump_type,
  parse_version,
  promote_release,
  read_current_version,
)


def make_spec(prompts_dir: Path) -> PromptSpec:
  return PromptSpec(
    prompts_dir=prompts_dir,
    files=("system.yaml",),
    required_variables=[],
    max_file_bytes=1000,
    release_gates=ReleaseGates(evidence=()),
  )


def test_parse_version_accepts_prefixed_and_unprefixed_versions() -> None:
  assert parse_version("v1.2.3") == (1, 2, 3)
  assert parse_version("1.2.3") == (1, 2, 3)
  assert normalize_version("1.2.3") == "v1.2.3"


def test_release_version_normalizes_sorts_and_bumps_versions() -> None:
  versions = [ReleaseVersion.parse("v1.0.0"), ReleaseVersion.parse("0.10.0")]

  assert str(ReleaseVersion.parse("1.2.3")) == "v1.2.3"
  assert [str(version) for version in sorted(versions)] == ["v0.10.0", "v1.0.0"]
  assert str(ReleaseVersion.parse("v1.2.3").bump(BumpType.MINOR)) == "v1.3.0"


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


def test_list_versions_returns_semver_sorted_valid_directories(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  versions_dir = prompts_dir / "versions"
  versions_dir.mkdir(parents=True)
  for name in ["v1.0.0", "v0.10.0", "v0.2.0", "notes", "vbad"]:
    (versions_dir / name).mkdir()

  assert list_versions(make_spec(prompts_dir)) == ["v0.2.0", "v0.10.0", "v1.0.0"]


def test_list_versions_returns_empty_list_without_versions_dir(tmp_path: Path) -> None:
  assert list_versions(make_spec(tmp_path / "prompts")) == []


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


def test_create_staged_release_does_not_update_current_pointer(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()

  version = create_release(manager.spec(), staged=True)

  release_dir = prompts_dir / "versions" / version
  lifecycle = (release_dir / "lifecycle.jsonl").read_text()
  assert version == "v0.0.1"
  assert (release_dir / "system.yaml").exists()
  assert (release_dir / "evidence").is_dir()
  assert not (prompts_dir / "current.json").exists()
  assert '"event": "release_staged"' in lifecycle


def test_create_release_records_lifecycle_and_promotes_by_default(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()

  version = create_release(manager.spec())

  lifecycle = (prompts_dir / "versions" / version / "lifecycle.jsonl").read_text()
  assert '"event": "release_created"' in lifecycle
  assert '"event": "promoted"' in lifecycle


def test_promote_release_updates_current_pointer_and_lifecycle(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  version = create_release(manager.spec(), staged=True)

  promote_release(manager.spec(), version)

  pointer = json.loads((prompts_dir / "current.json").read_text())
  lifecycle = (prompts_dir / "versions" / version / "lifecycle.jsonl").read_text()
  assert pointer["version"] == version
  assert '"event": "promoted"' in lifecycle


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


def test_create_release_removes_partial_release_after_non_os_error(
  tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()

  def fail_metadata(release_dir: Path, version: str, files: tuple[str, ...]) -> dict[str, object]:
    raise PromptReleaseError("metadata failed")

  monkeypatch.setattr(release_module, "write_metadata", fail_metadata)

  with pytest.raises(PromptReleaseError):
    create_release(manager.spec())

  assert not (prompts_dir / "versions" / "v0.0.1").exists()


def test_create_staged_release_removes_partial_release_after_non_os_error(
  tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()

  def fail_metadata(release_dir: Path, version: str, files: tuple[str, ...]) -> dict[str, object]:
    raise PromptReleaseError("metadata failed")

  monkeypatch.setattr(release_module, "write_metadata", fail_metadata)

  with pytest.raises(PromptReleaseError):
    create_release(manager.spec(), staged=True)

  assert not (prompts_dir / "versions" / "v0.0.1").exists()


def test_read_current_version_rejects_malformed_pointer(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  prompts_dir.mkdir()
  (prompts_dir / "current.json").write_text("[]\n")

  with pytest.raises(PromptReleaseError):
    read_current_version(make_spec(prompts_dir))
