"""Release metadata helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from promptory.config import validate_prompt_file_name
from promptory.errors import PromptReleaseError, PromptSpecError


@dataclass(frozen=True)
class IntegrityIssue:
  """One release artifact integrity problem."""

  file_name: str
  reason: str


@dataclass(frozen=True)
class IntegrityResult:
  """Release artifact integrity result."""

  version: str
  passed: bool
  issues: tuple[IntegrityIssue, ...]


def sha256_file(path: Path) -> str:
  """Compute SHA-256 for a file."""
  digest = sha256()
  with path.open("rb") as file_handle:
    for chunk in iter(lambda: file_handle.read(65_536), b""):
      digest.update(chunk)
  return digest.hexdigest()


def write_metadata(release_dir: Path, version: str, files: tuple[str, ...]) -> dict[str, Any]:
  """Write metadata.json for a release."""
  checksums = {
    file_name: sha256_file(release_dir / file_name)
    for file_name in files
    if (release_dir / file_name).exists()
  }
  metadata = {
    "version": version,
    "created_at": datetime.now(UTC).isoformat(),
    "files": list(files),
    "checksums": checksums,
  }
  (release_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
  return metadata


def verify_metadata(release_dir: Path) -> IntegrityResult:
  """Verify release prompt artifacts against metadata.json.

  Raises:
    PromptReleaseError: If metadata.json is missing or malformed.
  """
  metadata = _read_metadata(release_dir)
  metadata_version = _metadata_string(metadata, "version")
  files = _metadata_files(metadata)
  checksums = _metadata_checksums(metadata)

  issues: list[IntegrityIssue] = []
  if metadata_version != release_dir.name:
    issues.append(IntegrityIssue(file_name="metadata.json", reason="version mismatch"))
  if not files:
    issues.append(IntegrityIssue(file_name="metadata.json", reason="files list is empty"))

  for file_name in files:
    artifact_path = release_dir / file_name
    recorded_checksum = checksums.get(file_name)
    if not isinstance(recorded_checksum, str) or not recorded_checksum:
      issues.append(IntegrityIssue(file_name=file_name, reason="checksum missing"))
      continue
    if not artifact_path.exists():
      issues.append(IntegrityIssue(file_name=file_name, reason="file missing"))
      continue
    if not artifact_path.is_file():
      issues.append(IntegrityIssue(file_name=file_name, reason="not a file"))
      continue

    actual_checksum = sha256_file(artifact_path)
    if actual_checksum != recorded_checksum:
      issues.append(IntegrityIssue(file_name=file_name, reason="checksum mismatch"))

  return IntegrityResult(version=release_dir.name, passed=not issues, issues=tuple(issues))


def _read_metadata(release_dir: Path) -> dict[str, Any]:
  metadata_path = release_dir / "metadata.json"
  if not metadata_path.exists():
    raise PromptReleaseError(f"Release metadata is missing: {metadata_path}")
  try:
    metadata = json.loads(metadata_path.read_text())
  except json.JSONDecodeError as exc:
    raise PromptReleaseError(f"Release metadata is invalid: {metadata_path}") from exc
  if not isinstance(metadata, dict):
    raise PromptReleaseError(f"Release metadata must be an object: {metadata_path}")
  return metadata


def _metadata_string(metadata: dict[str, Any], field_name: str) -> str:
  value = metadata.get(field_name)
  if not isinstance(value, str) or not value:
    raise PromptReleaseError(f"Release metadata field must be a non-empty string: {field_name}")
  return value


def _metadata_files(metadata: dict[str, Any]) -> tuple[str, ...]:
  files = metadata.get("files")
  if not isinstance(files, list) or not all(isinstance(file_name, str) for file_name in files):
    raise PromptReleaseError("Release metadata files must be a list of strings")
  try:
    return tuple(validate_prompt_file_name(file_name) for file_name in files)
  except PromptSpecError as exc:
    raise PromptReleaseError(f"Release metadata file is invalid: {exc}") from exc


def _metadata_checksums(metadata: dict[str, Any]) -> dict[str, Any]:
  checksums = metadata.get("checksums")
  if not isinstance(checksums, dict):
    raise PromptReleaseError("Release metadata checksums must be an object")
  return checksums
