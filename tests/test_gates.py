import json
from pathlib import Path

import pytest

from promptory.errors import PromptGateError
from promptory.evidence import add_evidence, revoke_evidence
from promptory.gates import check_release_gates, require_release_gates
from promptory.manager import PromptManager


def write_gate_spec(prompts_dir: Path, *, required_status: str = "pass") -> None:
  (prompts_dir / "promptspec.yaml").write_text(
    "files:\n"
    "  - system.yaml\n"
    "required_variables: []\n"
    "max_file_bytes: 1000\n"
    "release_gates:\n"
    "  evidence:\n"
    "    - kind: eval\n"
    "      name: customer-support-regression\n"
    f"      required_status: {required_status}\n"
  )


def write_evidence(path: Path, *, status: str = "pass") -> None:
  path.write_text(
    json.dumps(
      {
        "kind": "eval",
        "name": "customer-support-regression",
        "status": status,
        "tool": "internal-eval-runner",
        "created_at": "2026-05-24T12:00:00Z",
      }
    )
  )


def test_release_gates_pass_when_no_gates_are_configured(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  version = manager.release(staged=True)

  result = check_release_gates(manager.spec(), version)

  assert result.passed is True
  assert result.checks == ()


def test_release_gates_pass_when_required_evidence_matches(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  write_gate_spec(prompts_dir)
  version = manager.release(staged=True)
  evidence_path = tmp_path / "evidence.json"
  write_evidence(evidence_path)
  add_evidence(manager.spec(), version, evidence_path)

  result = check_release_gates(manager.spec(), version)

  assert result.passed is True
  assert result.checks[0].passed is True
  assert result.checks[0].reason is None


def test_release_gates_fail_when_required_evidence_is_missing(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  write_gate_spec(prompts_dir)
  version = manager.release(staged=True)

  result = check_release_gates(manager.spec(), version)

  assert result.passed is False
  assert result.checks[0].reason == "required evidence missing"


def test_release_gates_fail_when_status_does_not_match(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  write_gate_spec(prompts_dir)
  version = manager.release(staged=True)
  evidence_path = tmp_path / "evidence.json"
  write_evidence(evidence_path, status="fail")
  add_evidence(manager.spec(), version, evidence_path)

  result = check_release_gates(manager.spec(), version)

  assert result.passed is False
  assert result.checks[0].reason == "evidence status is fail, required pass"


def test_release_gates_fail_when_evidence_is_revoked(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  write_gate_spec(prompts_dir)
  version = manager.release(staged=True)
  evidence_path = tmp_path / "evidence.json"
  write_evidence(evidence_path)
  add_evidence(manager.spec(), version, evidence_path)
  revoke_evidence(manager.spec(), version, "customer-support-regression", "Fixture set was stale.")

  result = check_release_gates(manager.spec(), version)

  assert result.passed is False
  assert result.checks[0].reason == "evidence was revoked"


def test_require_release_gates_raises_when_gates_fail(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  write_gate_spec(prompts_dir)
  version = manager.release(staged=True)

  with pytest.raises(PromptGateError):
    require_release_gates(manager.spec(), version)


def test_require_release_gates_returns_result_when_gates_pass(tmp_path: Path) -> None:
  prompts_dir = tmp_path / "prompts"
  manager = PromptManager(prompts_dir)
  manager.init()
  write_gate_spec(prompts_dir)
  version = manager.release(staged=True)
  evidence_path = tmp_path / "evidence.json"
  write_evidence(evidence_path)
  add_evidence(manager.spec(), version, evidence_path)

  result = require_release_gates(manager.spec(), version)

  assert result.passed is True
