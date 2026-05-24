"""End-to-end Promptory lifecycle example.

Demonstrates: init, draft, release, PromptStore runtime API, version pinning.

Run with:
    uv run python examples/lifecycle.py
"""

import tempfile
from pathlib import Path

from promptory import PromptStore
from promptory.manager import PromptManager


def main() -> None:
  with tempfile.TemporaryDirectory() as tmp:
    prompts_dir = Path(tmp) / "prompts"

    # --- Authoring ---
    manager = PromptManager(prompts_dir)
    manager.init()

    # Write a draft with a required variable.
    draft = prompts_dir / "drafts" / "system.yaml.j2"
    draft.write_text(
      "model: gpt-5.5\ntemperature: 0.2\nsystem_prompt: |\n  You are a {{ persona }} assistant.\n"
    )

    # Declare the variable in promptspec.
    spec_path = prompts_dir / "promptspec.yaml"
    spec_path.write_text(
      "files:\n  - system.yaml\nrequired_variables:\n  - persona\nmax_file_bytes: 100000\n"
    )

    errors = manager.check()
    assert not errors, errors

    v1 = manager.release(bump="patch", variables={"persona": "helpful"})
    print(f"Released {v1}")

    # --- Runtime: Python consumer ---
    store = PromptStore(prompts_dir)
    prompt = store.load("system.yaml")
    print(f"Active prompt: {prompt}")

    # Iterate the draft and cut a second release.
    draft.write_text(
      "model: gpt-5.5\n"
      "temperature: 0.1\n"
      "system_prompt: |\n"
      "  You are a {{ persona }} assistant. Be concise.\n"
    )
    v2 = manager.release(bump="patch", variables={"persona": "helpful"})
    print(f"Released {v2}")

    # Pin to a specific version for evals or replay.
    v1_prompt = store.load("system.yaml", version=v1)
    v2_prompt = store.load("system.yaml", version=v2)
    print(f"v1 temperature: {v1_prompt['temperature']}")
    print(f"v2 temperature: {v2_prompt['temperature']}")

    print(f"All versions: {store.list_versions()}")
    print(f"Current:      {store.current_version()}")

    # Rollback to v1 and confirm the store reflects the change.
    manager.rollback(v1)
    print(f"After rollback, current: {store.current_version()}")


if __name__ == "__main__":
  main()
