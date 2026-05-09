from pathlib import Path

import pytest

from promptkit.config import load_spec, validate_prompt_file_name
from promptkit.errors import PromptSpecError


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


def test_load_spec_accepts_nested_yaml_files(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  write_spec(
    prompts_dir,
    "files:\n  - agents/support/system.yaml\nrequired_variables: []\nmax_file_bytes: 1000\n",
  )

  spec = load_spec(prompts_dir)

  assert spec.files == ("agents/support/system.yaml",)
  assert spec.max_file_bytes == 1000


@pytest.mark.parametrize(
  "content",
  [
    "[]\n",
    "files: []\n",
    "files:\n  - system.yaml\n  - system.yaml\n",
    "files:\n  - system.yaml\nrequired_variables: name\n",
    "files:\n  - system.yaml\nmax_file_bytes: 0\n",
    "files:\n  - system.yaml\nmax_file_bytes: nope\n",
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
