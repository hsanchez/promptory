"""Runtime loading for released prompt artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from promptkit.config import load_spec, validate_prompt_file_name
from promptkit.errors import PromptLoadError, PromptReleaseError
from promptkit.release import read_current_version


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

  def load(self, file_name: str) -> dict[str, Any]:
    """Load one rendered prompt YAML file from the active release.

    Raises:
      PromptLoadError: If the file is undeclared, missing, or invalid YAML.
      PromptSpecError: If the prompt spec or file name is invalid.
    """
    spec = load_spec(self.prompts_dir)
    validated_file_name = validate_prompt_file_name(file_name)
    if validated_file_name not in spec.files:
      raise PromptLoadError(f"Prompt file is not declared in promptspec.yaml: {file_name}")

    try:
      version = read_current_version(spec)
    except PromptReleaseError as exc:
      raise PromptLoadError(f"Cannot read current prompt version: {exc}") from exc
    if version is None:
      raise PromptLoadError(f"No current prompt release exists: {spec.current_pointer_path}")

    prompt_path = spec.versions_dir / version / validated_file_name
    if not prompt_path.exists():
      raise PromptLoadError(f"Released prompt file is missing: {prompt_path}")

    try:
      loaded = yaml.safe_load(prompt_path.read_text())
    except yaml.YAMLError as exc:
      raise PromptLoadError(f"Released prompt YAML is invalid: {prompt_path}") from exc
    if not isinstance(loaded, dict):
      raise PromptLoadError(f"Released prompt YAML must be a mapping: {prompt_path}")
    return loaded

  def load_all(self) -> dict[str, dict[str, Any]]:
    """Load every prompt declared in promptspec.yaml.

    Raises:
      PromptLoadError: If any released prompt cannot be loaded.
      PromptSpecError: If promptspec.yaml is invalid.
    """
    spec = load_spec(self.prompts_dir)
    return {file_name: self.load(file_name) for file_name in spec.files}
