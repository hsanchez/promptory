"""Promptory configuration loading."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import cast

import yaml

from promptory.errors import PromptSpecError

EVIDENCE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class EvidenceStatus(StrEnum):
  """Supported release evidence statuses."""

  PASS = "pass"
  FAIL = "fail"
  WARNING = "warning"
  INFO = "info"


EVIDENCE_STATUSES = {status.value for status in EvidenceStatus}


@dataclass(frozen=True)
class EvidenceGate:
  """Evidence requirement for release promotion."""

  kind: str
  name: str
  required_status: EvidenceStatus


@dataclass(frozen=True)
class ReleaseGates:
  """Configured gates for release promotion."""

  evidence: tuple[EvidenceGate, ...]


@dataclass(frozen=True)
class PromptSpec:
  """Configuration for a prompt repository."""

  prompts_dir: Path
  files: tuple[str, ...]
  required_variables: list[str]
  max_file_bytes: int
  release_gates: ReleaseGates

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

  def release_dir(self, version: str) -> Path:
    return self.versions_dir / version

  def release_metadata_path(self, version: str) -> Path:
    return self.release_dir(version) / "metadata.json"

  def release_lifecycle_path(self, version: str) -> Path:
    return self.release_dir(version) / "lifecycle.jsonl"

  def release_evidence_dir(self, version: str) -> Path:
    return self.release_dir(version) / "evidence"


def default_spec() -> dict[str, object]:
  """Return a default promptspec document."""
  return {
    "files": ["system.yaml"],
    "required_variables": [],
    "max_file_bytes": 100_000,
  }


def validate_evidence_name(name: str) -> str:
  """Validate an evidence identifier from promptspec.yaml.

  Raises:
    PromptSpecError: If the evidence name is unsafe or unsupported.
  """
  if not name:
    raise PromptSpecError("Evidence name must not be empty")
  if name in {".", ".."}:
    raise PromptSpecError(f"Evidence name is invalid: {name}")
  path = Path(name)
  if path.is_absolute():
    raise PromptSpecError(f"Evidence name must be relative: {name}")
  if ".." in path.parts:
    raise PromptSpecError(f"Evidence name cannot contain '..': {name}")
  if any(part in {"", "."} for part in path.parts):
    raise PromptSpecError(f"Evidence name is invalid: {name}")
  if any(separator in name for separator in ("/", "\\")):
    raise PromptSpecError(f"Evidence name cannot contain path separators: {name}")
  if not EVIDENCE_NAME_RE.match(name):
    raise PromptSpecError(f"Evidence name is invalid: {name}")
  return name


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

  release_gates = _load_release_gates(raw.get("release_gates", {}))

  return PromptSpec(
    prompts_dir=prompts_dir,
    files=validated_files,
    required_variables=required_variables,
    max_file_bytes=max_file_bytes,
    release_gates=release_gates,
  )


def _load_release_gates(raw: object) -> ReleaseGates:
  if raw is None:
    return ReleaseGates(evidence=())
  if not isinstance(raw, dict):
    raise PromptSpecError("promptspec.yaml release_gates must be a mapping")

  raw_gates = cast(dict[str, object], raw)
  evidence = raw_gates.get("evidence")
  if evidence is None:
    evidence = []
  if not isinstance(evidence, list):
    raise PromptSpecError("promptspec.yaml release_gates.evidence must be a list")

  evidence_gates: list[EvidenceGate] = []
  for item in evidence:
    if not isinstance(item, dict):
      raise PromptSpecError("promptspec.yaml release_gates.evidence items must be mappings")
    gate = cast(dict[str, object], item)
    kind = gate.get("kind")
    name = gate.get("name")
    required_status = gate.get("required_status")
    if not isinstance(kind, str) or not kind:
      raise PromptSpecError("Evidence gate kind must be a non-empty string")
    if not isinstance(name, str):
      raise PromptSpecError("Evidence gate name must be a string")
    if not isinstance(required_status, str) or not required_status:
      raise PromptSpecError("Evidence gate required_status must be a non-empty string")
    try:
      evidence_status = EvidenceStatus(required_status)
    except ValueError as exc:
      raise PromptSpecError(
        f"Evidence gate required_status is unsupported: {required_status}"
      ) from exc
    evidence_gates.append(
      EvidenceGate(
        kind=kind,
        name=validate_evidence_name(name),
        required_status=evidence_status,
      )
    )

  return ReleaseGates(evidence=tuple(evidence_gates))
