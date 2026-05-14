"""Prompt diff helpers."""

from __future__ import annotations

from difflib import unified_diff

from promptory.config import PromptSpec
from promptory.release import read_current_version
from promptory.render import render_prompts


def diff_lines(content: str) -> list[str]:
  """Return lines safe for unified_diff output."""
  lines = content.splitlines(keepends=True)
  if lines and not lines[-1].endswith("\n"):
    lines[-1] = f"{lines[-1]}\n"
  return lines


def diff_current_against_drafts(spec: PromptSpec) -> str:
  """Return a unified diff between the current release and rendered drafts."""
  rendered = render_prompts(spec)
  chunks: list[str] = []
  current_version = read_current_version(spec)
  current_dir = spec.versions_dir / current_version if current_version else None

  for file_name, draft_content in rendered.items():
    current_path = current_dir / file_name if current_dir is not None else None
    current_content = (
      current_path.read_text() if current_path is not None and current_path.exists() else ""
    )

    chunks.extend(
      unified_diff(
        diff_lines(current_content),
        diff_lines(draft_content),
        fromfile=f"{current_version or 'current'}/{file_name}",
        tofile=f"drafts/{file_name}",
      )
    )

  return "".join(chunks)
