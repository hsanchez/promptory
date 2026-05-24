"""Promptory CLI."""

from __future__ import annotations

import importlib
import os
from pathlib import Path
from typing import Any, cast

import typer
from rich.console import Console
from rich.syntax import Syntax

from promptory.manager import PromptManager
from promptory.store import PromptStore

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command()
def init(prompts_dir: Path = Path("prompts")) -> None:
  """Initialize prompt directories."""
  PromptManager(prompts_dir).init()
  console.print("[green]Initialized Promptory prompt structure.[/green]")


@app.command()
def draft(prompts_dir: Path = Path("prompts")) -> None:
  """Create drafts from the current release."""
  PromptManager(prompts_dir).draft_from_current()
  console.print("[green]Drafts created from the current release.[/green]")


@app.command()
def check(prompts_dir: Path = Path("prompts")) -> None:
  """Validate prompt drafts."""
  errors = PromptManager(prompts_dir).check()
  if errors:
    for error in errors:
      console.print(f"[red]ERROR[/red] {error}")
    raise typer.Exit(code=1)
  console.print("[green]Prompt check passed.[/green]")


@app.command()
def release(
  prompts_dir: Path = Path("prompts"),
  patch: bool = False,
  minor: bool = False,
  major: bool = False,
) -> None:
  """Create a new immutable prompt release."""
  selected = [
    name
    for name, enabled in {
      "patch": patch,
      "minor": minor,
      "major": major,
    }.items()
    if enabled
  ]

  bump = selected[0] if selected else "patch"
  if len(selected) > 1:
    console.print("[red]Choose only one bump type.[/red]")
    raise typer.Exit(code=1)

  manager = PromptManager(prompts_dir)
  errors = manager.check()
  if errors:
    for error in errors:
      console.print(f"[red]ERROR[/red] {error}")
    raise typer.Exit(code=1)

  version = manager.release(bump=bump)
  console.print(f"[green]Created prompt release {version}.[/green]")


@app.command()
def diff(prompts_dir: Path = Path("prompts")) -> None:
  """Show a colored diff between the current release and rendered drafts."""
  output = PromptManager(prompts_dir).diff()
  if not output:
    console.print("[green]No prompt changes.[/green]")
    return
  console.print(Syntax(output, "diff"))


@app.command()
def rollback(version: str, prompts_dir: Path = Path("prompts")) -> None:
  """Point current.json at an existing release."""
  PromptManager(prompts_dir).rollback(version)
  console.print(f"[green]Pointed current.json at {version}.[/green]")


@app.command()
def versions(prompts_dir: Path = Path("prompts")) -> None:
  """List available prompt releases."""
  available_versions = PromptStore(prompts_dir).list_versions()
  if not available_versions:
    console.print("[yellow]No releases found.[/yellow]")
    return
  for version in available_versions:
    console.print(version)


@app.command()
def serve(
  prompts_dir: Path = Path("prompts"),
  host: str = "0.0.0.0",
  port: int = 8000,
  reload: bool = False,
) -> None:
  """Start the prompt sidecar adapter."""
  try:
    uvicorn = cast(Any, importlib.import_module("uvicorn"))
    importlib.import_module("promptory.serve")
  except ImportError:
    console.print("[red]Sidecar adapter dependencies not found.[/red]")
    console.print("Install Promptory with the [bold]serve[/bold] extra.")
    raise typer.Exit(code=1) from None

  os.environ["PROMPTORY_PROMPTS_DIR"] = str(prompts_dir)

  console.print(f"[green]Starting prompt sidecar adapter on {host}:{port}[/green]")
  uvicorn.run("promptory.serve:app", host=host, port=port, reload=reload)


def main() -> None:
  """CLI entrypoint."""
  app()


if __name__ == "__main__":
  main()
