from pathlib import Path

import pytest

from promptory import PromptStore
from promptory.errors import PromptLoadError, PromptSpecError
from promptory.manager import PromptManager


def write_multi_prompt_spec(prompts_dir: Path) -> None:
  (prompts_dir / "promptspec.yaml").write_text(
    "files:\n"
    "  - system.yaml\n"
    "  - input_guardrail.yaml\n"
    "required_variables: []\n"
    "max_file_bytes: 1000\n"
  )


def test_store_loads_declared_prompt_from_current_release(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  manager.release()

  store = PromptStore(prompts_dir)

  assert store.current_version() == "v0.0.1"
  assert store.load("system.yaml")["model"] == "gpt-5.5"


def test_store_loads_all_declared_prompts(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  write_multi_prompt_spec(prompts_dir)
  (prompts_dir / "drafts" / "input_guardrail.yaml.j2").write_text("policy: |\n  Reject secrets.\n")
  manager.release()

  prompts = PromptStore(prompts_dir).load_all()

  assert set(prompts) == {"system.yaml", "input_guardrail.yaml"}
  assert prompts["input_guardrail.yaml"]["policy"] == "Reject secrets."


def test_store_lists_available_versions(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  manager.release()
  manager.release()

  assert PromptStore(prompts_dir).list_versions() == ["v0.0.1", "v0.0.2"]


def test_store_loads_specific_version(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  first_version = manager.release()
  (prompts_dir / "drafts" / "system.yaml.j2").write_text("model: gpt-5.5\nsystem_prompt: second\n")
  second_version = manager.release()

  store = PromptStore(prompts_dir)

  assert first_version == "v0.0.1"
  assert second_version == "v0.0.2"
  assert store.load("system.yaml", version=first_version)["system_prompt"].strip() == (
    "You are a helpful assistant."
  )
  assert store.load("system.yaml", version=second_version)["system_prompt"] == "second"


def test_store_loads_specific_unprefixed_version(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  manager.release()

  assert PromptStore(prompts_dir).load("system.yaml", version="0.0.1")["model"] == "gpt-5.5"


def test_store_loads_all_from_specific_version(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  write_multi_prompt_spec(prompts_dir)
  (prompts_dir / "drafts" / "input_guardrail.yaml.j2").write_text("policy: first\n")
  first_version = manager.release()
  (prompts_dir / "drafts" / "input_guardrail.yaml.j2").write_text("policy: second\n")
  manager.release()

  prompts = PromptStore(prompts_dir).load_all(version=first_version)

  assert prompts["input_guardrail.yaml"]["policy"] == "first"


def test_store_rejects_invalid_specific_version(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  manager.release()

  with pytest.raises(PromptLoadError):
    PromptStore(prompts_dir).load("system.yaml", version="../v0.0.1")


def test_store_rejects_unknown_specific_version(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  manager.release()

  with pytest.raises(PromptLoadError):
    PromptStore(prompts_dir).load("system.yaml", version="v9.9.9")


def test_store_rejects_undeclared_prompt_file(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  manager.release()

  with pytest.raises(PromptLoadError):
    PromptStore(prompts_dir).load("input_guardrail.yaml")


def test_store_rejects_unsafe_prompt_file_name(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()

  with pytest.raises(PromptSpecError):
    PromptStore(prompts_dir).load("../system.yaml")


def test_store_requires_current_release(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()

  with pytest.raises(PromptLoadError):
    PromptStore(prompts_dir).current_version()


def test_store_rejects_missing_released_prompt_file(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  manager.release()
  (prompts_dir / "versions" / "v0.0.1" / "system.yaml").unlink()

  with pytest.raises(PromptLoadError):
    PromptStore(prompts_dir).load("system.yaml")


def test_store_rejects_non_mapping_yaml(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  manager.release()
  (prompts_dir / "versions" / "v0.0.1" / "system.yaml").write_text("- item\n")

  with pytest.raises(PromptLoadError):
    PromptStore(prompts_dir).load("system.yaml")
