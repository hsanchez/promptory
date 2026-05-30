import json
from pathlib import Path

import pytest

from promptory.errors import PromptEvidenceError
from promptory.evidence import add_evidence, list_evidence, revoke_evidence, show_evidence
from promptory.manager import PromptManager


@pytest.fixture
def staged_release(tmp_path: Path) -> tuple[Path, PromptManager, str]:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  version = manager.release(staged=True)
  return prompts_dir, manager, version


def write_evidence(path: Path, *, name: str = "customer-support-regression") -> None:
  path.write_text(
    json.dumps(
      {
        "kind": "eval",
        "name": name,
        "status": "pass",
        "tool": "internal-eval-runner",
        "created_at": "2026-05-24T12:00:00Z",
        "summary": "No regressions.",
        "metrics": {
          "pass_rate": 0.94,
          "failed_cases": 3,
        },
      }
    )
  )


def test_add_list_and_show_evidence(
  tmp_path: Path, staged_release: tuple[Path, PromptManager, str]
) -> None:
  prompts_dir, manager, version = staged_release
  source_path = tmp_path / "evidence.json"
  write_evidence(source_path)

  summary = add_evidence(manager.spec(), version, source_path)
  summaries = list_evidence(manager.spec(), version)
  evidence = show_evidence(manager.spec(), version, "customer-support-regression")

  assert summary.name == "customer-support-regression"
  assert len(summaries) == 1
  assert summaries[0].status == "pass"
  assert evidence["metrics"]["pass_rate"] == 0.94
  assert (
    prompts_dir / "versions" / version / "evidence" / "customer-support-regression.json"
  ).exists()


def test_add_evidence_rejects_invalid_schema(
  tmp_path: Path, staged_release: tuple[Path, PromptManager, str]
) -> None:
  _prompts_dir, manager, version = staged_release
  source_path = tmp_path / "evidence.json"
  source_path.write_text(json.dumps({"name": "customer-support-regression"}))

  with pytest.raises(PromptEvidenceError):
    add_evidence(manager.spec(), version, source_path)


def test_add_evidence_rejects_duplicate_name(
  tmp_path: Path, staged_release: tuple[Path, PromptManager, str]
) -> None:
  _prompts_dir, manager, version = staged_release
  source_path = tmp_path / "evidence.json"
  write_evidence(source_path)

  add_evidence(manager.spec(), version, source_path)

  with pytest.raises(PromptEvidenceError):
    add_evidence(manager.spec(), version, source_path)


def test_add_evidence_rejects_unsafe_name(
  tmp_path: Path, staged_release: tuple[Path, PromptManager, str]
) -> None:
  _prompts_dir, manager, version = staged_release
  source_path = tmp_path / "evidence.json"
  write_evidence(source_path, name="../customer-support-regression")

  with pytest.raises(PromptEvidenceError):
    add_evidence(manager.spec(), version, source_path)


def test_revoke_evidence_records_revocation_without_deleting_original(
  tmp_path: Path, staged_release: tuple[Path, PromptManager, str]
) -> None:
  prompts_dir, manager, version = staged_release
  source_path = tmp_path / "evidence.json"
  write_evidence(source_path)
  add_evidence(manager.spec(), version, source_path)

  revoke_evidence(manager.spec(), version, "customer-support-regression", "Fixture set was stale.")

  release_dir = prompts_dir / "versions" / version
  summaries = list_evidence(manager.spec(), version)
  lifecycle = (release_dir / "lifecycle.jsonl").read_text()
  assert (release_dir / "evidence" / "customer-support-regression.json").exists()
  assert (release_dir / "evidence" / "customer-support-regression.revocation.json").exists()
  assert summaries[0].revoked is True
  assert summaries[0].revocation_reason == "Fixture set was stale."
  assert '"event": "evidence_revoked"' in lifecycle


def test_revoke_evidence_rejects_unknown_evidence(
  staged_release: tuple[Path, PromptManager, str],
) -> None:
  _prompts_dir, manager, version = staged_release

  with pytest.raises(PromptEvidenceError):
    revoke_evidence(manager.spec(), version, "customer-support-regression", "No longer valid.")
