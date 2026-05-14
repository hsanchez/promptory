"""Promptory configuration loading."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from promptory.errors import PromptSpecError


@dataclass(frozen=True)
class PromptSpec:
  """Configuration for a prompt repository."""

  prompts_dir: Path
  files: tuple[str, ...]
  required_variables: list[str]
  max_file_bytes: int

  @property
  def drafts_dir(self) -> Path:
    return self.prompts_dir / "drafts"

  @property
  def versions_dir(self) -> Path:
    return self.prompts_dir / "versions"

  @property
  def current_pointer_path(self) -> Path:
    return self.prompts_dir / "current.json"

  @property
  def spec_path(self) -> Path:
    return self.prompts_dir / "promptspec.yaml"


def default_spec() -> dict[str, object]:
  """Return a default promptspec document."""
  return {
    "files": ["system.yaml"],
    "required_variables": [],
    "max_file_bytes": 100_000,
  }


def validate_prompt_file_name(file_name: str) -> str:
  """Validate a rendered prompt file name from promptspec.yaml.

  Raises:
    PromptSpecError: If the file name is unsafe or unsupported.
  """
  path = Path(file_name)
  if path.is_absolute():
    raise PromptSpecError(f"Prompt file must be relative: {file_name}")
  if ".." in path.parts:
    raise PromptSpecError(f"Prompt file cannot contain '..': {file_name}")
  if path.name == "metadata.json":
    raise PromptSpecError("metadata.json is reserved for release metadata")
  if path.suffix != ".yaml":
    raise PromptSpecError(f"Prompt file must end with .yaml: {file_name}")
  if path.name == ".yaml" or any(part in {"", "."} for part in path.parts):
    raise PromptSpecError(f"Prompt file is invalid: {file_name}")
  return path.as_posix()


def load_spec(prompts_dir: Path) -> PromptSpec:
  """Load promptspec.yaml.

  Raises:
    PromptSpecError: If promptspec.yaml is missing or invalid.
  """
  spec_path = prompts_dir / "promptspec.yaml"
  if not spec_path.exists():
    raise PromptSpecError(f"Missing promptspec: {spec_path}")

  raw = yaml.safe_load(spec_path.read_text())
  if raw is None:
    raw = {}
  if not isinstance(raw, dict):
    raise PromptSpecError("promptspec.yaml must be a mapping")

  files = raw.get("files")
  if not isinstance(files, list) or not all(isinstance(item, str) for item in files):
    raise PromptSpecError("promptspec.yaml must contain files: list[str]")
  if not files:
    raise PromptSpecError("promptspec.yaml files must not be empty")

  validated_files = tuple(validate_prompt_file_name(file_name) for file_name in files)
  if len(validated_files) != len(set(validated_files)):
    raise PromptSpecError("promptspec.yaml files must be unique")

  required_variables = raw.get("required_variables", [])
  if not isinstance(required_variables, list) or not all(
    isinstance(item, str) for item in required_variables
  ):
    raise PromptSpecError("promptspec.yaml required_variables must be list[str]")

  max_file_bytes = raw.get("max_file_bytes", 100_000)
  if not isinstance(max_file_bytes, int) or max_file_bytes <= 0:
    raise PromptSpecError("promptspec.yaml max_file_bytes must be a positive int")

  return PromptSpec(
    prompts_dir=prompts_dir,
    files=validated_files,
    required_variables=required_variables,
    max_file_bytes=max_file_bytes,
  )
