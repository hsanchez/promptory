"""Prompt release creation."""

from __future__ import annotations

import json
import re
import shutil
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from promptkit.config import PromptSpec
from promptkit.errors import PromptReleaseError
from promptkit.metadata import write_metadata
from promptkit.render import render_prompts

VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


class BumpType(StrEnum):
  """Supported semantic version bump types."""

  MAJOR = "major"
  MINOR = "minor"
  PATCH = "patch"


def parse_version(version: str) -> tuple[int, int, int]:
  """Parse semantic version.

  Raises:
    PromptReleaseError: If version is not a semantic version.
  """
  match = VERSION_RE.match(version)
  if match is None:
    raise PromptReleaseError(f"Invalid version: {version}")
  major, minor, patch = match.groups()
  return int(major), int(minor), int(patch)


def format_version(version: tuple[int, int, int]) -> str:
  """Format semantic version with v prefix."""
  return f"v{version[0]}.{version[1]}.{version[2]}"


def normalize_version(version: str) -> str:
  """Return a canonical v-prefixed semantic version.

  Raises:
    PromptReleaseError: If version is not a semantic version.
  """
  return format_version(parse_version(version))


def latest_version(spec: PromptSpec) -> str | None:
  """Return latest version, if any."""
  if not spec.versions_dir.exists():
    return None
  versions = []
  for child in spec.versions_dir.iterdir():
    if child.is_dir() and VERSION_RE.match(child.name):
      versions.append(child.name)
  if not versions:
    return None
  return sorted(versions, key=parse_version)[-1]


def bump_version(current: str | None, bump: BumpType) -> str:
  """Bump a semantic version."""
  major, minor, patch = parse_version(current or "v0.0.0")
  if bump is BumpType.MAJOR:
    return format_version((major + 1, 0, 0))
  if bump is BumpType.MINOR:
    return format_version((major, minor + 1, 0))
  if bump is BumpType.PATCH:
    return format_version((major, minor, patch + 1))
  raise PromptReleaseError(f"Unknown bump type: {bump.value}")


def parse_bump_type(bump: str | BumpType) -> BumpType:
  """Return a supported bump type.

  Raises:
    PromptReleaseError: If bump is not supported.
  """
  if isinstance(bump, BumpType):
    return bump
  try:
    return BumpType(bump)
  except ValueError as exc:
    raise PromptReleaseError(f"Unknown bump type: {bump}") from exc


def write_current_pointer(spec: PromptSpec, version: str) -> None:
  """Point current.json at an existing release.

  Raises:
    PromptReleaseError: If the release does not exist.
  """
  normalized_version = normalize_version(version)
  release_dir = spec.versions_dir / normalized_version
  if not release_dir.is_dir():
    raise PromptReleaseError(f"Unknown release: {normalized_version}")

  pointer = {
    "version": normalized_version,
    "updated_at": datetime.now(UTC).isoformat(),
  }
  spec.current_pointer_path.write_text(json.dumps(pointer, indent=2) + "\n")


def read_current_version(spec: PromptSpec) -> str | None:
  """Read current.json.

  Raises:
    PromptReleaseError: If current.json is malformed.
  """
  if not spec.current_pointer_path.exists():
    return None
  try:
    raw = json.loads(spec.current_pointer_path.read_text())
  except json.JSONDecodeError as exc:
    raise PromptReleaseError(f"Invalid current pointer: {spec.current_pointer_path}") from exc
  if not isinstance(raw, dict) or not isinstance(raw.get("version"), str):
    raise PromptReleaseError(f"Invalid current pointer: {spec.current_pointer_path}")
  return normalize_version(raw["version"])


def create_release(
  spec: PromptSpec,
  bump: str | BumpType = BumpType.PATCH,
  variables: dict[str, Any] | None = None,
) -> str:
  """Render drafts, create a version release, and update current.json.

  Raises:
    PromptReleaseError: If the release cannot be created.
  """
  version = bump_version(latest_version(spec), parse_bump_type(bump))
  release_dir = spec.versions_dir / version

  if release_dir.exists():
    raise PromptReleaseError(f"Release already exists: {release_dir}")

  rendered = render_prompts(spec, variables=variables)

  release_dir.mkdir(parents=True)
  try:
    for file_name, content in rendered.items():
      output_path = release_dir / file_name
      output_path.parent.mkdir(parents=True, exist_ok=True)
      output_path.write_text(content)
    write_metadata(release_dir, version, spec.files)

    write_current_pointer(spec, version)
  except OSError:
    if release_dir.exists():
      shutil.rmtree(release_dir)
    raise

  return version
