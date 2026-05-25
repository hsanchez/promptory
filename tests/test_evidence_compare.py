import json
from pathlib import Path

import pytest

from promptory.errors import PromptEvidenceError
from promptory.evidence import add_evidence, compare_evidence, revoke_evidence
from promptory.manager import PromptManager


def write_evidence(
  path: Path,
  *,
  name: str,
  status: str = "pass",
  pass_rate: float = 0.94,
  failed_cases: int = 3,
) -> None:
  path.write_text(
    json.dumps(
      {
        "kind": "eval",
        "name": name,
        "status": status,
        "tool": "internal-eval-runner",
        "created_at": "2026-05-24T12:00:00Z",
        "metrics": {
          "pass_rate": pass_rate,
          "failed_cases": failed_cases,
          "nested": {
            "ignored": True,
          },
        },
      }
    )
  )


def make_two_releases(tmp_path: Path) -> tuple[PromptManager, str, str]:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  first_version = manager.release(staged=True)
  second_version = manager.release(staged=True)
  return manager, first_version, second_version


def test_compare_evidence_reports_added_evidence(tmp_path: Path) -> None:
  manager, first_version, second_version = make_two_releases(tmp_path)
  evidence_path = tmp_path / "after.json"
  write_evidence(evidence_path, name="customer-support-regression")
  add_evidence(manager.spec(), second_version, evidence_path)

  comparison = compare_evidence(manager.spec(), first_version, second_version)

  assert len(comparison.changes) == 1
  change = comparison.changes[0]
  assert change.name == "customer-support-regression"
  assert change.before_status is None
  assert change.after_status == "pass"


def test_compare_evidence_reports_missing_evidence(tmp_path: Path) -> None:
  manager, first_version, second_version = make_two_releases(tmp_path)
  evidence_path = tmp_path / "before.json"
  write_evidence(evidence_path, name="customer-support-regression")
  add_evidence(manager.spec(), first_version, evidence_path)

  comparison = compare_evidence(manager.spec(), first_version, second_version)

  assert len(comparison.changes) == 1
  change = comparison.changes[0]
  assert change.before_status == "pass"
  assert change.after_status is None


def test_compare_evidence_reports_status_and_metric_changes(tmp_path: Path) -> None:
  manager, first_version, second_version = make_two_releases(tmp_path)
  before_path = tmp_path / "before.json"
  after_path = tmp_path / "after.json"
  write_evidence(
    before_path,
    name="customer-support-regression",
    status="pass",
    pass_rate=0.91,
    failed_cases=5,
  )
  write_evidence(
    after_path,
    name="customer-support-regression",
    status="fail",
    pass_rate=0.94,
    failed_cases=3,
  )
  add_evidence(manager.spec(), first_version, before_path)
  add_evidence(manager.spec(), second_version, after_path)

  comparison = compare_evidence(manager.spec(), first_version, second_version)

  assert len(comparison.changes) == 1
  change = comparison.changes[0]
  assert change.before_status == "pass"
  assert change.after_status == "fail"
  assert [(metric.name, metric.before, metric.after) for metric in change.metrics] == [
    ("failed_cases", 5, 3),
    ("pass_rate", 0.91, 0.94),
  ]


def test_compare_evidence_reports_revocation_change(tmp_path: Path) -> None:
  manager, first_version, second_version = make_two_releases(tmp_path)
  before_path = tmp_path / "before.json"
  after_path = tmp_path / "after.json"
  write_evidence(before_path, name="customer-support-regression")
  write_evidence(after_path, name="customer-support-regression")
  add_evidence(manager.spec(), first_version, before_path)
  add_evidence(manager.spec(), second_version, after_path)
  revoke_evidence(manager.spec(), second_version, "customer-support-regression", "Stale fixtures.")

  comparison = compare_evidence(manager.spec(), first_version, second_version)

  assert len(comparison.changes) == 1
  change = comparison.changes[0]
  assert change.before_revoked is False
  assert change.after_revoked is True


def test_compare_evidence_omits_unchanged_evidence(tmp_path: Path) -> None:
  manager, first_version, second_version = make_two_releases(tmp_path)
  before_path = tmp_path / "before.json"
  after_path = tmp_path / "after.json"
  write_evidence(before_path, name="customer-support-regression")
  write_evidence(after_path, name="customer-support-regression")
  add_evidence(manager.spec(), first_version, before_path)
  add_evidence(manager.spec(), second_version, after_path)

  comparison = compare_evidence(manager.spec(), first_version, second_version)

  assert comparison.changes == ()


def test_compare_evidence_omits_changes_for_same_version(tmp_path: Path) -> None:
  manager, first_version, _second_version = make_two_releases(tmp_path)
  evidence_path = tmp_path / "evidence.json"
  write_evidence(evidence_path, name="customer-support-regression")
  add_evidence(manager.spec(), first_version, evidence_path)

  comparison = compare_evidence(manager.spec(), first_version, first_version)

  assert comparison.changes == ()


def test_compare_evidence_rejects_unknown_version(tmp_path: Path) -> None:
  manager, first_version, _second_version = make_two_releases(tmp_path)

  with pytest.raises(PromptEvidenceError):
    compare_evidence(manager.spec(), first_version, "v9.9.9")
