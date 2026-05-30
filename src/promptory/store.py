"""Runtime loading for released prompt artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from promptory.config import PromptSpec, load_spec, validate_prompt_file_name
from promptory.errors import PromptLoadError, PromptReleaseError
from promptory.release import list_versions, normalize_version, read_current_version


class PromptStore:
  """Load released prompt YAML from the active version."""

  def __init__(self, prompts_dir: Path | str = Path("prompts")) -> None:
    self.prompts_dir = Path(prompts_dir)

  def current_version(self) -> str:
    """Return the active release version.

    Raises:
      PromptLoadError: If no current release exists or the pointer is invalid.
    """
    spec = load_spec(self.prompts_dir)
    try:
      version = read_current_version(spec)
    except PromptReleaseError as exc:
      raise PromptLoadError(f"Cannot read current prompt version: {exc}") from exc
    if version is None:
      raise PromptLoadError(f"No current prompt release exists: {spec.current_pointer_path}")
    return version

  def load(self, file_name: str, version: str | None = None) -> dict[str, Any]:
    """Load one rendered prompt YAML file.

    Raises:
      PromptLoadError: If the file is undeclared, missing, or invalid YAML.
      PromptSpecError: If the prompt spec or file name is invalid.
    """
    spec = load_spec(self.prompts_dir)
    validated_file_name = validate_prompt_file_name(file_name)
    if validated_file_name not in spec.files:
      raise PromptLoadError(f"Prompt file is not declared in promptspec.yaml: {file_name}")

    resolved_version = self._resolve_version(spec, version)
    return self._load_declared_file(spec, validated_file_name, resolved_version)

  def load_all(self, version: str | None = None) -> dict[str, dict[str, Any]]:
    """Load every prompt declared in promptspec.yaml.

    Raises:
      PromptLoadError: If any released prompt cannot be loaded.
      PromptSpecError: If promptspec.yaml is invalid.
    """
    spec = load_spec(self.prompts_dir)
    resolved_version = self._resolve_version(spec, version)
    return {
      file_name: self._load_declared_file(spec, file_name, resolved_version)
      for file_name in spec.files
    }

  def list_versions(self) -> list[str]:
    """Return valid release versions sorted by semantic version.

    Raises:
      PromptSpecError: If promptspec.yaml is invalid.
    """
    return list_versions(load_spec(self.prompts_dir))

  def _resolve_version(self, spec: PromptSpec, version: str | None) -> str:
    if version is not None:
      try:
        resolved_version = normalize_version(version)
      except PromptReleaseError as exc:
        raise PromptLoadError(f"Invalid prompt release version: {version}") from exc
    else:
      try:
        resolved_version = read_current_version(spec)
      except PromptReleaseError as exc:
        raise PromptLoadError(f"Cannot read current prompt version: {exc}") from exc
      if resolved_version is None:
        raise PromptLoadError(f"No current prompt release exists: {spec.current_pointer_path}")

    release_dir = spec.release_dir(resolved_version)
    if not release_dir.is_dir():
      raise PromptLoadError(f"Unknown prompt release: {resolved_version}")
    return resolved_version

  def _load_declared_file(self, spec: PromptSpec, file_name: str, version: str) -> dict[str, Any]:
    prompt_path = spec.release_dir(version) / file_name
    if not prompt_path.exists():
      raise PromptLoadError(f"Released prompt file is missing: {prompt_path}")

    try:
      loaded = yaml.safe_load(prompt_path.read_text())
    except yaml.YAMLError as exc:
      raise PromptLoadError(f"Released prompt YAML is invalid: {prompt_path}") from exc
    if not isinstance(loaded, dict):
      raise PromptLoadError(f"Released prompt YAML must be a mapping: {prompt_path}")
    return loaded
