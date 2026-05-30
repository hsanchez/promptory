from pathlib import Path

import pytest

from promptory.config import load_spec, validate_evidence_name, validate_prompt_file_name
from promptory.errors import PromptSpecError


def write_spec(prompts_dir: Path, content: str) -> None:
  prompts_dir.mkdir()
  (prompts_dir / "promptspec.yaml").write_text(content)


@pytest.mark.parametrize(
  "file_name",
  [
    "../system.yaml",
    "/system.yaml",
    "system.yml",
    "system.md",
    "metadata.json",
    ".yaml",
  ],
)
def test_prompt_file_name_rejects_unsupported_paths(file_name: str) -> None:
  with pytest.raises(PromptSpecError):
    validate_prompt_file_name(file_name)


@pytest.mark.parametrize(
  "name",
  [
    "../customer-support-regression",
    "/customer-support-regression",
    "customer/support",
    "-regression",
    "_regression",
    ".hidden",
    ".",
    "",
  ],
)
def test_evidence_name_rejects_unsupported_names(name: str) -> None:
  with pytest.raises(PromptSpecError):
    validate_evidence_name(name)


def test_load_spec_accepts_nested_yaml_files(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  write_spec(
    prompts_dir,
    "files:\n  - agents/support/system.yaml\nrequired_variables: []\nmax_file_bytes: 1000\n",
  )

  spec = load_spec(prompts_dir)

  assert spec.files == ("agents/support/system.yaml",)
  assert spec.max_file_bytes == 1000
  assert spec.release_gates.evidence == ()


def test_load_spec_accepts_release_gates(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  write_spec(
    prompts_dir,
    "files:\n"
    "  - system.yaml\n"
    "required_variables: []\n"
    "max_file_bytes: 1000\n"
    "release_gates:\n"
    "  evidence:\n"
    "    - kind: eval\n"
    "      name: customer-support-regression\n"
    "      required_status: pass\n",
  )

  spec = load_spec(prompts_dir)

  assert len(spec.release_gates.evidence) == 1
  gate = spec.release_gates.evidence[0]
  assert gate.kind == "eval"
  assert gate.name == "customer-support-regression"
  assert gate.required_status == "pass"


@pytest.mark.parametrize(
  "content",
  [
    "[]\n",
    "files: []\n",
    "files:\n  - system.yaml\n  - system.yaml\n",
    "files:\n  - system.yaml\nrequired_variables: name\n",
    "files:\n  - system.yaml\nmax_file_bytes: 0\n",
    "files:\n  - system.yaml\nmax_file_bytes: nope\n",
    "files:\n  - system.yaml\nrelease_gates: []\n",
    "files:\n  - system.yaml\nrelease_gates:\n  evidence: nope\n",
    "files:\n  - system.yaml\nrelease_gates:\n  evidence:\n    - nope\n",
    "files:\n  - system.yaml\nrelease_gates:\n  evidence:\n    - kind: ''\n      name: check\n      required_status: pass\n",
    "files:\n  - system.yaml\nrelease_gates:\n  evidence:\n    - kind: eval\n      name: ../check\n      required_status: pass\n",
    "files:\n  - system.yaml\nrelease_gates:\n  evidence:\n    - kind: eval\n      name: check\n      required_status: unknown\n",
  ],
)
def test_load_spec_rejects_invalid_documents(tmp_path: Path, content: str) -> None:
  prompts_dir = tmp_path / "prompts"
  write_spec(prompts_dir, content)

  with pytest.raises(PromptSpecError):
    load_spec(prompts_dir)


def test_load_spec_rejects_missing_promptspec(tmp_path: Path) -> None:
  with pytest.raises(PromptSpecError):
    load_spec(tmp_path / "prompts")
