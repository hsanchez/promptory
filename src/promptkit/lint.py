"""Prompt linting."""

from __future__ import annotations

import yaml
from jinja2.exceptions import TemplateSyntaxError

from promptkit.config import PromptSpec
from promptkit.render import required_template_variables, template_name_for


def lint_prompts(spec: PromptSpec) -> list[str]:
  """Return a list of lint errors. Empty list means success."""
  errors: list[str] = []
  all_found_variables: set[str] = set()

  for file_name in spec.files:
    template_path = spec.drafts_dir / template_name_for(file_name)
    if not template_path.exists():
      errors.append(f"Missing draft template: {template_path}")
      continue

    if template_path.stat().st_size > spec.max_file_bytes:
      errors.append(f"Draft exceeds max_file_bytes: {template_path}")

    source = template_path.read_text()
    try:
      found_variables = required_template_variables(source, spec.drafts_dir)
    except TemplateSyntaxError as exc:
      errors.append(f"Invalid Jinja syntax in {template_path}: {exc}")
      continue

    all_found_variables.update(found_variables)

    undeclared_required = found_variables - set(spec.required_variables)
    if undeclared_required:
      errors.append(
        f"{template_path} references variables not listed in promptspec.yaml: "
        f"{sorted(undeclared_required)}"
      )

    try:
      rendered_without_vars = source
      yaml.safe_load(rendered_without_vars)
    except yaml.YAMLError as exc:
      if "{{" not in source and "{%" not in source:
        errors.append(f"Invalid YAML in {template_path}: {exc}")

  missing_required = set(spec.required_variables) - all_found_variables
  if missing_required:
    errors.append(
      f"promptspec.yaml lists required variables that no template references: "
      f"{sorted(missing_required)}"
    )

  return errors
