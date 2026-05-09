"""Release metadata helpers."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
  """Compute SHA-256 for a file."""
  return sha256(path.read_bytes()).hexdigest()


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
