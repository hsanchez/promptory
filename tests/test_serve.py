from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from promptory.manager import PromptManager
from promptory.serve import app


def make_client() -> TestClient:
  return TestClient(app)


def setup_release(tmp_path: Path, files: dict[str, str] | None = None) -> PromptManager:
  manager = PromptManager(tmp_path)
  manager.init()
  if files:
    spec_files = "\n".join(f"  - {name}" for name in files)
    (tmp_path / "promptspec.yaml").write_text(f"files:\n{spec_files}\n")
    for name, content in files.items():
      template = tmp_path / "drafts" / (name + ".j2")
      template.parent.mkdir(parents=True, exist_ok=True)
      template.write_text(content)
  else:
    (tmp_path / "promptspec.yaml").write_text("files:\n  - system.yaml\n")
    (tmp_path / "drafts" / "system.yaml.j2").write_text("role: assistant\n")
  manager.release(bump="patch")
  return manager


def test_root_returns_service_metadata() -> None:
  response = make_client().get("/")
  assert response.status_code == 200
  assert response.json()["service"] == "promptory"


def test_list_versions_returns_released_versions(
  tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
  monkeypatch.setenv("PROMPTORY_PROMPTS_DIR", str(tmp_path))
  setup_release(tmp_path)

  response = make_client().get("/versions")

  assert response.status_code == 200
  assert "v0.0.1" in response.json()


def test_current_version_returns_active_version(
  tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
  monkeypatch.setenv("PROMPTORY_PROMPTS_DIR", str(tmp_path))
  setup_release(tmp_path)

  response = make_client().get("/versions/current")

  assert response.status_code == 200
  assert response.json() == {"version": "v0.0.1"}


def test_current_version_returns_404_when_no_release(
  tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
  monkeypatch.setenv("PROMPTORY_PROMPTS_DIR", str(tmp_path))
  PromptManager(tmp_path).init()

  response = make_client().get("/versions/current")

  assert response.status_code == 404


def test_load_all_returns_all_prompts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
  monkeypatch.setenv("PROMPTORY_PROMPTS_DIR", str(tmp_path))
  setup_release(tmp_path, files={"system.yaml": "role: system\n", "user.yaml": "role: user\n"})

  response = make_client().get("/prompts")

  assert response.status_code == 200
  data = response.json()
  assert data["system.yaml"] == {"role": "system"}
  assert data["user.yaml"] == {"role": "user"}


def test_load_prompt_returns_single_prompt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
  monkeypatch.setenv("PROMPTORY_PROMPTS_DIR", str(tmp_path))
  setup_release(tmp_path, files={"system.yaml": "role: system\n"})

  response = make_client().get("/prompts/system.yaml")

  assert response.status_code == 200
  assert response.json() == {"role": "system"}


def test_load_prompt_returns_nested_prompt_path(
  tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
  monkeypatch.setenv("PROMPTORY_PROMPTS_DIR", str(tmp_path))
  setup_release(tmp_path, files={"agents/support/system.yaml": "role: support\n"})

  response = make_client().get("/prompts/agents/support/system.yaml")

  assert response.status_code == 200
  assert response.json() == {"role": "support"}


def test_load_prompt_path_traversal_rejected(
  tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
  monkeypatch.setenv("PROMPTORY_PROMPTS_DIR", str(tmp_path))

  response = make_client().get("/prompts/..%2F..%2Fetc%2Fpasswd")

  assert response.status_code == 400
