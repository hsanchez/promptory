from pathlib import Path

import pytest

from promptory.config import PromptSpec
from promptory.errors import PromptRenderError
from promptory.render import render_prompts, required_template_variables, template_name_for


def make_spec(prompts_dir: Path, files: tuple[str, ...] = ("system.yaml",)) -> PromptSpec:
  return PromptSpec(
    prompts_dir=prompts_dir,
    files=files,
    required_variables=[],
    max_file_bytes=1000,
  )


def test_template_name_for_appends_jinja_suffix() -> None:
  assert template_name_for("system.yaml") == "system.yaml.j2"


def test_jinja_default_variables_are_not_required(tmp_path: Path) -> None:
  drafts_dir = tmp_path / "drafts"
  drafts_dir.mkdir()
  source = "model: {{ model | default('gpt-5.5') }}\ngenerated_at: {{ generated_at }}\n"

  assert required_template_variables(source, drafts_dir) == {"generated_at"}


def test_render_prompts_uses_strict_undefined(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  drafts_dir = prompts_dir / "drafts"
  drafts_dir.mkdir(parents=True)
  (drafts_dir / "system.yaml.j2").write_text("model: {{ model }}\n")

  with pytest.raises(PromptRenderError):
    render_prompts(make_spec(prompts_dir))


def test_render_prompts_accepts_explicit_variables(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  drafts_dir = prompts_dir / "drafts"
  drafts_dir.mkdir(parents=True)
  (drafts_dir / "system.yaml.j2").write_text("model: {{ model }}\n")

  rendered = render_prompts(make_spec(prompts_dir), variables={"model": "gpt-5.5"})

  assert rendered == {"system.yaml": "model: gpt-5.5"}


def test_render_prompts_rejects_invalid_rendered_yaml(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  drafts_dir = prompts_dir / "drafts"
  drafts_dir.mkdir(parents=True)
  (drafts_dir / "system.yaml.j2").write_text("model: [broken\n")

  with pytest.raises(PromptRenderError):
    render_prompts(make_spec(prompts_dir))


def test_render_prompts_rejects_missing_template(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  (prompts_dir / "drafts").mkdir(parents=True)

  with pytest.raises(PromptRenderError):
    render_prompts(make_spec(prompts_dir))
