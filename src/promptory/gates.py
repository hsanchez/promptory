"""Release gate checks."""

from __future__ import annotations

from dataclasses import dataclass

from promptory.config import EvidenceGate, PromptSpec
from promptory.errors import PromptEvidenceError, PromptGateError, PromptReleaseError
from promptory.evidence import EvidenceSummary, list_evidence
from promptory.release import normalize_version


@dataclass(frozen=True)
class GateCheck:
  """Result for one configured release gate."""

  kind: str
  name: str
  required_status: str
  status: str | None
  passed: bool
  reason: str | None


@dataclass(frozen=True)
class GateResult:
  """Release gate result for one version."""

  version: str
  passed: bool
  checks: tuple[GateCheck, ...]


def check_release_gates(spec: PromptSpec, version: str) -> GateResult:
  """Check configured release gates for a version.

  Raises:
    PromptGateError: If the version or evidence cannot be checked.
  """
  try:
    normalized_version = normalize_version(version)
    evidence = list_evidence(spec, normalized_version)
  except (PromptEvidenceError, PromptReleaseError) as exc:
    raise PromptGateError(f"Cannot check release gates for {version}: {exc}") from exc

  evidence_by_key = {(item.kind, item.name): item for item in evidence}
  checks = tuple(
    _check_evidence_gate(gate, evidence_by_key) for gate in spec.release_gates.evidence
  )
  return GateResult(
    version=normalized_version,
    passed=all(check.passed for check in checks),
    checks=checks,
  )


def require_release_gates(spec: PromptSpec, version: str) -> GateResult:
  """Check gates and raise if any configured gate fails.

  Raises:
    PromptGateError: If any release gate fails or cannot be checked.
  """
  result = check_release_gates(spec, version)
  if not result.passed:
    failures = "; ".join(
      check.reason or "release gate failed" for check in result.checks if not check.passed
    )
    raise PromptGateError(f"Release gates failed for {result.version}: {failures}")
  return result


def _check_evidence_gate(
  gate: EvidenceGate,
  evidence_by_key: dict[tuple[str, str], EvidenceSummary],
) -> GateCheck:
  evidence = evidence_by_key.get((gate.kind, gate.name))
  if evidence is None:
    return GateCheck(
      kind=gate.kind,
      name=gate.name,
      required_status=gate.required_status,
      status=None,
      passed=False,
      reason="required evidence missing",
    )

  if evidence.revoked:
    return GateCheck(
      kind=gate.kind,
      name=gate.name,
      required_status=gate.required_status,
      status=evidence.status,
      passed=False,
      reason="evidence was revoked",
    )

  if evidence.status != gate.required_status:
    return GateCheck(
      kind=gate.kind,
      name=gate.name,
      required_status=gate.required_status,
      status=evidence.status,
      passed=False,
      reason=f"evidence status is {evidence.status}, required {gate.required_status}",
    )

  return GateCheck(
    kind=gate.kind,
    name=gate.name,
    required_status=gate.required_status,
    status=evidence.status,
    passed=True,
    reason=None,
  )
