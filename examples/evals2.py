"""Gating Your LLM Eval Rubric with Evidence.

Part 2 of "Managing Your LLM Eval Rubric Like Code."

You have a versioned rubric workflow (see evals.py). This example adds
a promotion rule: no rubric becomes current unless its eval evidence passes.

Demonstrates:
  1. Staged releases    - rubric candidates that are not yet active.
  2. Eval evidence      - attach external eval results as immutable artifacts.
  3. Release gates      - require passing evidence before promotion.
  4. Evidence comparison - understand why one version cleared the bar and another did not.

Run with:
    uv run python examples/evals2.py
"""

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from promptory import PromptStore
from promptory.evidence import add_evidence, compare_evidence
from promptory.manager import PromptManager

# Fixed benchmark: (question, model response) pairs with ground-truth quality labels.
# In practice these come from a curated evaluation dataset.
TEST_CASES = [
  {
    "input": "What is the powerhouse of the cell?",
    "response": "The mitochondria is the powerhouse of the cell.",
    "quality": "good",
  },
  {
    "input": "What is the powerhouse of the cell?",
    "response": "I dunno lol.",
    "quality": "bad",
  },
  {
    "input": "How do plants produce energy?",
    "response": "Photosynthesis converts sunlight into chemical energy.",
    "quality": "good",
  },
  {
    "input": "How do plants produce energy?",
    "response": "It just works somehow.",
    "quality": "bad",
  },
  {
    "input": "When did the French Revolution begin?",
    "response": "The French Revolution began in 1789.",
    "quality": "good",
  },
]

BASIC_RUBRIC = (
  "model: claude-sonnet-4-6\n"
  "temperature: 0.0\n"
  "system_prompt: |\n"
  "  Evaluate the response on {{ criteria }}.\n"
  "  Be generous; give partial credit for effort.\n"
  "  Return JSON: {score: int, rationale: str}.\n"
)

STRICT_RUBRIC = (
  "model: claude-sonnet-4-6\n"
  "temperature: 0.0\n"
  "system_prompt: |\n"
  "  Evaluate the response on {{ criteria }}.\n"
  "  Penalize vague or incomplete answers.\n"
  "  Return JSON: {score: int, rationale: str}.\n"
)

# Accuracy threshold for evidence status. Below this a candidate fails the gate.
PASS_THRESHOLD = 0.9


def simulate_judge_call(system_prompt: str, question: str, response: str) -> int:
  """Simulate one LLM judge call returning a score from 1 to 5.

  In production, replace this body with a real LLM call:
      user_message = f"Question: {question}\\nResponse: {response}"
      result = call_llm(system=system_prompt, user=user_message)
      return json.loads(result)["score"]
  """
  # Use keyword heuristics to approximate what an LLM judge would infer from the response text.
  is_substantive = not any(phrase in response.lower() for phrase in ["dunno", "somehow", "lol"])

  if "Penalize" in system_prompt:
    return 5 if is_substantive else 1  # strict: correctly distinguishes good from bad
  return 5 if is_substantive else 4  # lenient: bad responses get partial credit


def run_fake_eval_harness(rubric: dict[str, object]) -> dict[str, float]:
  """Score every test case using the rubric prompt as judge instructions."""
  system_prompt = str(rubric.get("system_prompt", ""))

  scores = [
    simulate_judge_call(system_prompt, case["input"], case["response"]) for case in TEST_CASES
  ]
  good_scores = [
    score for case, score in zip(TEST_CASES, scores, strict=True) if case["quality"] == "good"
  ]
  bad_scores = [
    score for case, score in zip(TEST_CASES, scores, strict=True) if case["quality"] == "bad"
  ]

  false_positive_rate = sum(1 for score in bad_scores if score >= 4) / len(bad_scores)
  false_negative_rate = sum(1 for score in good_scores if score < 4) / len(good_scores)
  accuracy = 1.0 - (
    false_positive_rate * len(bad_scores) + false_negative_rate * len(good_scores)
  ) / len(TEST_CASES)

  return {
    "accuracy": round(accuracy, 2),
    "false_positive_rate": round(false_positive_rate, 2),
    "false_negative_rate": round(false_negative_rate, 2),
    "mean_score": round(sum(scores) / len(scores), 2),
  }


def setup(prompts_dir: Path) -> tuple[PromptManager, PromptStore]:
  """Initialize a rubric prompt repo with a release gate.

  The gate requires eval evidence with status 'pass' before any rubric
  candidate can be promoted to current.
  """
  manager = PromptManager(prompts_dir)
  manager.init()

  (prompts_dir / "promptspec.yaml").write_text(
    "files:\n"
    "  - rubric.yaml\n"
    "required_variables:\n"
    "  - criteria\n"
    "max_file_bytes: 100000\n"
    "release_gates:\n"
    "  evidence:\n"
    "    - kind: eval\n"
    "      name: eval-run\n"
    "      required_status: pass\n"
  )

  return manager, PromptStore(prompts_dir)


def stage_and_evaluate(
  manager: PromptManager,
  store: PromptStore,
  evidence_dir: Path,
  draft_content: str,
  criteria: str,
  label: str,
) -> str:
  """Stage a rubric candidate, run evals, attach evidence, and check the gate.

  Returns:
    The staged version string.
  """
  draft = manager.prompts_dir / "drafts" / "rubric.yaml.j2"
  draft.write_text(draft_content)

  errors = manager.check()
  if errors:
    raise ValueError(f"Prompt spec errors: {errors}")

  version = manager.release(bump="patch", variables={"criteria": criteria}, staged=True)
  print(f"\n[{label}] staged {version}")

  # Load the staged rubric and run the external eval harness against it.
  rubric = store.load("rubric.yaml", version=version)
  metrics = run_fake_eval_harness(rubric)
  print(
    f"  accuracy={metrics['accuracy']:.0%}"
    f"  fpr={metrics['false_positive_rate']:.0%}"
    f"  fnr={metrics['false_negative_rate']:.0%}"
  )

  # Attach eval results as immutable evidence on this staged version.
  status = "pass" if metrics["accuracy"] >= PASS_THRESHOLD else "fail"
  evidence_doc: dict[str, object] = {
    "kind": "eval",
    "name": "eval-run",
    "status": status,
    "tool": "eval-harness",
    "created_at": datetime.now(UTC).isoformat(),
    "summary": f"accuracy={metrics['accuracy']:.0%}",
    "metrics": metrics,
  }
  evidence_path = evidence_dir / f"evidence_{version}.json"
  evidence_path.write_text(json.dumps(evidence_doc, indent=2))
  add_evidence(manager.spec(), version, evidence_path)

  gate = manager.gate(version)
  print(f"  gate: {'PASS' if gate.passed else 'FAIL - candidate stays staged'}")

  return version


def promote_best(
  manager: PromptManager,
  store: PromptStore,
  before: str,
  after: str,
) -> None:
  """Compare evidence between two candidates and promote the later one with gates enforced."""
  comparison = compare_evidence(manager.spec(), before, after)
  print(f"\nEvidence comparison {comparison.before_version} -> {comparison.after_version}:")
  for change in comparison.changes:
    print(f"  [{change.kind}] {change.name}: {change.before_status} -> {change.after_status}")
    for metric in change.metrics:
      print(f"    {metric.name}: {metric.before} -> {metric.after}")

  # Gates enforce the promotion rule: evidence must have status 'pass'.
  manager.promote(after, require_gates=True)
  print(f"\nPromoted {after} -> current: {store.current_version()}")


def main() -> None:
  with tempfile.TemporaryDirectory() as temp_dir:
    temp_path = Path(temp_dir)
    manager, store = setup(temp_path / "prompts")

    # v1: lenient rubric candidate - accuracy below threshold, gate fails, stays staged.
    version_1 = stage_and_evaluate(
      manager, store, temp_path, BASIC_RUBRIC, criteria="helpfulness", label="v1 basic"
    )

    # v2: strict rubric candidate - accuracy clears the gate, eligible for promotion.
    version_2 = stage_and_evaluate(
      manager, store, temp_path, STRICT_RUBRIC, criteria="helpfulness", label="v2 strict"
    )

    # Compare evidence between candidates, then promote the later one with gates enforced.
    promote_best(manager, store, before=version_1, after=version_2)


if __name__ == "__main__":
  main()
