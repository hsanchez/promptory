"""Prompt rendering."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined, meta, nodes
from jinja2.exceptions import TemplateError

from promptkit.config import PromptSpec
from promptkit.errors import PromptRenderError


def template_name_for(file_name: str) -> str:
  """Return the draft template name for a rendered prompt file."""
  return f"{file_name}.j2"


def undeclared_variables(template_source: str, drafts_dir: Path) -> set[str]:
  """Return Jinja undeclared variables."""
  env = Environment(loader=FileSystemLoader(str(drafts_dir)), undefined=StrictUndefined)
  ast = env.parse(template_source)
  return set(meta.find_undeclared_variables(ast))


def variables_with_defaults(template_source: str, drafts_dir: Path) -> set[str]:
  """Return Jinja variables that use the default filter."""
  env = Environment(loader=FileSystemLoader(str(drafts_dir)), undefined=StrictUndefined)
  ast = env.parse(template_source)
  variable_names: set[str] = set()
  for node in ast.find_all(nodes.Filter):
    if node.name == "default" and isinstance(node.node, nodes.Name):
      variable_names.add(node.node.name)
  return variable_names


def required_template_variables(template_source: str, drafts_dir: Path) -> set[str]:
  """Return Jinja variables that must be supplied by callers."""
  return undeclared_variables(template_source, drafts_dir) - variables_with_defaults(
    template_source, drafts_dir
  )


def render_prompts(spec: PromptSpec, variables: dict[str, Any] | None = None) -> dict[str, str]:
  """Render all prompt templates declared in promptspec.yaml.

  Raises:
    PromptRenderError: If a template is missing, cannot render, or renders invalid YAML.
  """
  variables = variables or {}
  env = Environment(loader=FileSystemLoader(str(spec.drafts_dir)), undefined=StrictUndefined)

  rendered: dict[str, str] = {}
  for file_name in spec.files:
    template_name = template_name_for(file_name)
    template_path = spec.drafts_dir / template_name
    if not template_path.exists():
      raise PromptRenderError(f"Missing draft template: {template_path}")

    try:
      rendered_content = env.get_template(template_name).render(**variables)
    except TemplateError as exc:
      raise PromptRenderError(f"Failed to render {template_name}: {exc}") from exc

    try:
      yaml.safe_load(rendered_content)
    except yaml.YAMLError as exc:
      raise PromptRenderError(f"Rendered YAML is invalid for {file_name}: {exc}") from exc

    rendered[file_name] = rendered_content

  return rendered
