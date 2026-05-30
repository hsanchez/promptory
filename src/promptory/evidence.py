"""Release evidence storage and validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from promptory.config import EVIDENCE_STATUSES, PromptSpec, validate_evidence_name
from promptory.errors import PromptEvidenceError, PromptReleaseError, PromptSpecError
from promptory.release import append_lifecycle_event, normalize_version


@dataclass(frozen=True)
class EvidenceSummary:
  """Summary of one release evidence artifact."""

  name: str
  kind: str
  status: str
  tool: str
  created_at: str
  summary: str | None
  revoked: bool
  revocation_reason: str | None


@dataclass(frozen=True)
class EvidenceRecord:
  """Evidence summary with scalar metrics for comparison."""

  summary: EvidenceSummary
  metrics: dict[str, object]


@dataclass(frozen=True)
class MetricChange:
  """Scalar metric difference between two evidence documents."""

  name: str
  before: object | None
  after: object | None


@dataclass(frozen=True)
class EvidenceChange:
  """Evidence difference between two release versions."""

  kind: str
  name: str
  before_status: str | None
  after_status: str | None
  before_revoked: bool | None
  after_revoked: bool | None
  metrics: tuple[MetricChange, ...]


@dataclass(frozen=True)
class EvidenceComparison:
  """Evidence comparison between two release versions."""

  before_version: str
  after_version: str
  changes: tuple[EvidenceChange, ...]


def add_evidence(spec: PromptSpec, version: str, source_path: Path) -> EvidenceSummary:
  """Store immutable evidence for a release.

  Raises:
    PromptEvidenceError: If the release or evidence document is invalid.
  """
  release_dir = _release_dir(spec, version)
  evidence = _read_json_document(source_path)
  _validate_evidence_document(evidence)
  name = _validate_evidence_name(evidence["name"])
  evidence_dir = _ensure_evidence_dir(release_dir)
  evidence_path = evidence_dir / f"{name}.json"
  if evidence_path.exists():
    raise PromptEvidenceError(f"Evidence already exists: {name}")

  evidence_path.write_text(json.dumps(evidence, indent=2) + "\n")
  append_lifecycle_event(
    release_dir,
    "evidence_added",
    {
      "version": release_dir.name,
      "name": name,
      "kind": evidence["kind"],
      "status": evidence["status"],
      "path": evidence_path.relative_to(release_dir).as_posix(),
    },
  )
  return _summary_from_evidence(release_dir, evidence)


def list_evidence(spec: PromptSpec, version: str) -> list[EvidenceSummary]:
  """List evidence attached to a release.

  Raises:
    PromptEvidenceError: If the release does not exist or evidence JSON is invalid.
  """
  release_dir = _release_dir(spec, version)
  evidence_dir = _evidence_dir_path(release_dir)
  if not evidence_dir.exists():
    return []
  summaries: list[EvidenceSummary] = []
  for evidence_path in sorted(evidence_dir.glob("*.json")):
    if evidence_path.name.endswith(".revocation.json"):
      continue
    evidence = _read_json_document(evidence_path)
    summaries.append(_summary_from_evidence(release_dir, evidence))
  return summaries


def show_evidence(spec: PromptSpec, version: str, name: str) -> dict[str, Any]:
  """Return one evidence document.

  Raises:
    PromptEvidenceError: If the release or evidence document is invalid.
  """
  release_dir = _release_dir(spec, version)
  evidence_name = _validate_evidence_name(name)
  evidence_path = _evidence_dir_path(release_dir) / f"{evidence_name}.json"
  if not evidence_path.exists():
    raise PromptEvidenceError(f"Unknown evidence: {evidence_name}")
  return _read_json_document(evidence_path)


def revoke_evidence(spec: PromptSpec, version: str, name: str, reason: str) -> None:
  """Record revocation for existing evidence.

  Raises:
    PromptEvidenceError: If the release, evidence, or revocation is invalid.
  """
  if not reason.strip():
    raise PromptEvidenceError("Revocation reason must not be empty")

  release_dir = _release_dir(spec, version)
  evidence_name = _validate_evidence_name(name)
  evidence_dir = _evidence_dir_path(release_dir)
  evidence_path = evidence_dir / f"{evidence_name}.json"
  if not evidence_path.exists():
    raise PromptEvidenceError(f"Unknown evidence: {evidence_name}")

  revocation_path = evidence_dir / f"{evidence_name}.revocation.json"
  if revocation_path.exists():
    raise PromptEvidenceError(f"Evidence is already revoked: {evidence_name}")

  revocation = {
    "kind": "revocation",
    "revokes": evidence_name,
    "reason": reason,
    "created_at": datetime.now(UTC).isoformat(),
  }
  revocation_path.write_text(json.dumps(revocation, indent=2) + "\n")
  append_lifecycle_event(
    release_dir,
    "evidence_revoked",
    {
      "version": release_dir.name,
      "name": evidence_name,
      "reason": reason,
      "path": revocation_path.relative_to(release_dir).as_posix(),
    },
  )


def compare_evidence(
  spec: PromptSpec,
  before_version: str,
  after_version: str,
) -> EvidenceComparison:
  """Compare evidence attached to two releases.

  Raises:
    PromptEvidenceError: If either release or evidence set cannot be read.
  """
  before_dir = _release_dir(spec, before_version)
  after_dir = _release_dir(spec, after_version)
  before_evidence = _evidence_records_by_key(before_dir)
  after_evidence = _evidence_records_by_key(after_dir)

  changes: list[EvidenceChange] = []
  for kind, name in sorted(before_evidence.keys() | after_evidence.keys()):
    before = before_evidence.get((kind, name))
    after = after_evidence.get((kind, name))
    change = _compare_evidence_item(kind, name, before, after)
    if change is not None:
      changes.append(change)

  return EvidenceComparison(
    before_version=before_dir.name,
    after_version=after_dir.name,
    changes=tuple(changes),
  )


def _release_dir(spec: PromptSpec, version: str) -> Path:
  try:
    normalized_version = normalize_version(version)
  except PromptReleaseError as exc:
    raise PromptEvidenceError(f"Invalid release version: {version}") from exc
  release_dir = spec.release_dir(normalized_version)
  if not release_dir.is_dir():
    raise PromptEvidenceError(f"Unknown release: {normalized_version}")
  return release_dir


def _evidence_dir_path(release_dir: Path) -> Path:
  return release_dir / "evidence"


def _ensure_evidence_dir(release_dir: Path) -> Path:
  evidence_dir = release_dir / "evidence"
  evidence_dir.mkdir(exist_ok=True)
  return evidence_dir


def _read_json_document(path: Path) -> dict[str, Any]:
  try:
    document = json.loads(path.read_text())
  except json.JSONDecodeError as exc:
    raise PromptEvidenceError(f"Evidence JSON is invalid: {path}") from exc
  if not isinstance(document, dict):
    raise PromptEvidenceError(f"Evidence JSON must be an object: {path}")
  return document


def _validate_evidence_document(document: dict[str, Any]) -> None:
  for field_name in ("kind", "name", "status", "tool", "created_at"):
    if not isinstance(document.get(field_name), str) or not document[field_name]:
      raise PromptEvidenceError(f"Evidence field must be a non-empty string: {field_name}")

  _validate_evidence_name(document["name"])
  if document["status"] not in EVIDENCE_STATUSES:
    raise PromptEvidenceError(f"Evidence status is unsupported: {document['status']}")

  try:
    datetime.fromisoformat(document["created_at"])
  except ValueError as exc:
    raise PromptEvidenceError("Evidence created_at must be an ISO timestamp") from exc

  summary = document.get("summary")
  if summary is not None and not isinstance(summary, str):
    raise PromptEvidenceError("Evidence summary must be a string")

  metrics = document.get("metrics")
  if metrics is not None and not isinstance(metrics, dict):
    raise PromptEvidenceError("Evidence metrics must be an object")


def _validate_evidence_name(name: str) -> str:
  try:
    return validate_evidence_name(name)
  except PromptSpecError as exc:
    raise PromptEvidenceError(str(exc)) from exc


def _summary_from_evidence(release_dir: Path, evidence: dict[str, Any]) -> EvidenceSummary:
  name = evidence["name"]
  revocation_path = _evidence_dir_path(release_dir) / f"{name}.revocation.json"
  revoked = revocation_path.exists()
  revocation_reason: str | None = None
  if revoked:
    revocation = _read_json_document(revocation_path)
    reason = revocation.get("reason")
    if isinstance(reason, str):
      revocation_reason = reason

  summary = evidence.get("summary")
  return EvidenceSummary(
    name=name,
    kind=evidence["kind"],
    status=evidence["status"],
    tool=evidence["tool"],
    created_at=evidence["created_at"],
    summary=summary if isinstance(summary, str) else None,
    revoked=revoked,
    revocation_reason=revocation_reason,
  )


def _evidence_records_by_key(release_dir: Path) -> dict[tuple[str, str], EvidenceRecord]:
  evidence_dir = _evidence_dir_path(release_dir)
  if not evidence_dir.exists():
    return {}
  records: dict[tuple[str, str], EvidenceRecord] = {}
  for evidence_path in sorted(evidence_dir.glob("*.json")):
    if evidence_path.name.endswith(".revocation.json"):
      continue
    evidence = _read_json_document(evidence_path)
    summary = _summary_from_evidence(release_dir, evidence)
    records[(summary.kind, summary.name)] = EvidenceRecord(
      summary=summary,
      metrics=_scalar_metrics(evidence),
    )
  return records


def _compare_evidence_item(
  kind: str,
  name: str,
  before: EvidenceRecord | None,
  after: EvidenceRecord | None,
) -> EvidenceChange | None:
  before_summary = before.summary if before is not None else None
  after_summary = after.summary if after is not None else None
  metric_changes = _compare_metric_values(
    before.metrics if before is not None else {},
    after.metrics if after is not None else {},
  )
  before_status = before_summary.status if before_summary is not None else None
  after_status = after_summary.status if after_summary is not None else None
  before_revoked = before_summary.revoked if before_summary is not None else None
  after_revoked = after_summary.revoked if after_summary is not None else None

  if before_status == after_status and before_revoked == after_revoked and not metric_changes:
    return None

  return EvidenceChange(
    kind=kind,
    name=name,
    before_status=before_status,
    after_status=after_status,
    before_revoked=before_revoked,
    after_revoked=after_revoked,
    metrics=metric_changes,
  )


def _scalar_metrics(document: dict[str, Any]) -> dict[str, object]:
  metrics = document.get("metrics")
  if not isinstance(metrics, dict):
    return {}
  return {
    name: value
    for name, value in metrics.items()
    if isinstance(name, str) and _is_scalar_metric(value)
  }


def _compare_metric_values(
  before: dict[str, object],
  after: dict[str, object],
) -> tuple[MetricChange, ...]:
  changes: list[MetricChange] = []
  for name in sorted(before.keys() | after.keys()):
    before_value = before.get(name)
    after_value = after.get(name)
    if before_value != after_value:
      changes.append(MetricChange(name=name, before=before_value, after=after_value))
  return tuple(changes)


def _is_scalar_metric(value: object) -> bool:
  return value is None or isinstance(value, str | int | float | bool)
