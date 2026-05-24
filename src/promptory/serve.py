"""FastAPI-based prompt sidecar adapter for non-Python consumers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query

from promptory.errors import PromptLoadError, PromptSpecError
from promptory.store import PromptStore

app = FastAPI(
  title="Promptory Serve",
  description="HTTP sidecar adapter: exposes a service's own released prompts to non-Python consumers.",
  version="0.1.0",
)


def get_store() -> PromptStore:
  """Return a PromptStore instance.

  Configured via PROMPTORY_PROMPTS_DIR environment variable.
  Defaults to 'prompts'.
  """
  prompts_dir = os.getenv("PROMPTORY_PROMPTS_DIR", "prompts")
  return PromptStore(Path(prompts_dir))


@app.get("/")
async def root() -> dict[str, str]:
  """Service metadata and health check."""
  return {
    "service": "promptory",
    "status": "healthy",
    "description": "HTTP sidecar adapter for non-Python consumers",
  }


@app.get("/versions")
async def list_versions() -> list[str]:
  """List all available semantic versions."""
  try:
    return get_store().list_versions()
  except PromptSpecError as exc:
    raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/versions/current")
async def current_version() -> dict[str, str]:
  """Get the active version string."""
  try:
    return {"version": get_store().current_version()}
  except PromptLoadError as exc:
    raise HTTPException(status_code=404, detail=str(exc)) from exc
  except PromptSpecError as exc:
    raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/prompts")
async def load_all(version: str | None = Query(None)) -> dict[str, dict[str, Any]]:
  """Load every prompt for a version (defaults to current)."""
  try:
    return get_store().load_all(version=version)
  except PromptLoadError as exc:
    raise HTTPException(status_code=404, detail=str(exc)) from exc
  except PromptSpecError as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/prompts/{name:path}")
async def load_prompt(name: str, version: str | None = Query(None)) -> dict[str, Any]:
  """Get a specific prompt by name."""
  try:
    return get_store().load(name, version=version)
  except PromptLoadError as exc:
    raise HTTPException(status_code=404, detail=str(exc)) from exc
  except PromptSpecError as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc
