"""Managing your LLM eval rubric like code with Promptory.

Promptory treats your eval rubric as a versioned software artifact.
This example demonstrates four concrete benefits:

  1. Template variables       - one rubric definition covers multiple eval criteria.
  2. Draft/release separation - iterate the rubric without overwriting past measurements.
  3. Reproducibility          - load any version by its exact identifier to replay an eval run.
  4. History and discoverability - list_versions() without filesystem management.

Run with:
    uv run python examples/evals.py
"""

import tempfile
from pathlib import Path

from promptory import PromptStore
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
  """Initialize a rubric prompt repo."""
  manager = PromptManager(prompts_dir)
  manager.init()

  (prompts_dir / "promptspec.yaml").write_text(
    "files:\n  - rubric.yaml\nrequired_variables:\n  - criteria\nmax_file_bytes: 100000\n"
  )

  return manager, PromptStore(prompts_dir)


def stage_and_evaluate(
  manager: PromptManager,
  store: PromptStore,
  draft_content: str,
  criteria: str,
  label: str,
) -> tuple[str, dict[str, float]]:
  """Release a rubric draft and run the eval harness against it.

  Returns:
    The version string and its eval metrics.
  """
  draft = manager.prompts_dir / "drafts" / "rubric.yaml.j2"
  draft.write_text(draft_content)

  errors = manager.check()
  if errors:
    raise ValueError(f"Prompt spec errors: {errors}")

  # criteria is a template variable rendered into the rubric at release time.
  # This example focuses on rubric versioning. For promotion workflows with
  # quality gates, use staged=True, attach eval evidence, and call manager.promote().
  version = manager.release(bump="patch", variables={"criteria": criteria})
  print(f"\n[{label}] released {version}")

  # Load the versioned rubric and pass its system_prompt to the eval harness.
  rubric = store.load("rubric.yaml", version=version)
  metrics = run_fake_eval_harness(rubric)
  print(
    f"  criteria={criteria!r}"
    f"  accuracy={metrics['accuracy']:.0%}"
    f"  fpr={metrics['false_positive_rate']:.0%}"
    f"  fnr={metrics['false_negative_rate']:.0%}"
  )

  return version, metrics


def report_results(
  store: PromptStore,
  results: list[tuple[str, dict[str, float], str]],
) -> None:
  """Show history, reproducibility, and best-version selection across all rubric releases."""
  # Benefit: history and discoverability.
  print(f"\nAll rubric versions: {store.list_versions()}")

  print(f"\n{'version':<12} {'criteria':<20} {'accuracy':>10} {'fpr':>8} {'fnr':>8}")
  for version, metrics, criteria in results:
    print(
      f"{version:<12}"
      f"  {criteria:<18}"
      f"  {metrics['accuracy']:>8.0%}"
      f"  {metrics['false_positive_rate']:>8.0%}"
      f"  {metrics['false_negative_rate']:>8.0%}"
    )

  # Benefit: reproducibility - any past version is loadable by its exact identifier.
  first_version = results[0][0]
  first_rubric = store.load("rubric.yaml", version=first_version)
  print(
    f"\nReproducibility: {first_version} is still loadable"
    f" even though {store.current_version()} is current."
  )
  print(f"  system_prompt: {first_rubric['system_prompt'].strip()}")

  # Identify the best rubric for helpfulness across the versions that measured it.
  helpfulness_results = [
    (version, metrics) for version, metrics, criteria in results if criteria == "helpfulness"
  ]
  best_version, _ = max(helpfulness_results, key=lambda result: result[1]["accuracy"])
  best_rubric = store.load("rubric.yaml", version=best_version)
  print(f"\nBest rubric for helpfulness: {best_version}")
  print(f"  system_prompt: {best_rubric['system_prompt'].strip()}")


def main() -> None:
  with tempfile.TemporaryDirectory() as temp_dir:
    manager, store = setup(Path(temp_dir) / "prompts")

    results: list[tuple[str, dict[str, float], str]] = []

    # Benefit: draft/release separation - each release is an immutable snapshot.
    # Iterating the draft never overwrites what was already measured.

    # v1: first rubric attempt - lenient, measured on helpfulness.
    version, metrics = stage_and_evaluate(
      manager, store, BASIC_RUBRIC, criteria="helpfulness", label="v1 basic"
    )
    results.append((version, metrics, "helpfulness"))

    # v2: tightened rubric - same criteria, updated draft. v1 remains intact.
    version, metrics = stage_and_evaluate(
      manager, store, STRICT_RUBRIC, criteria="helpfulness", label="v2 strict"
    )
    results.append((version, metrics, "helpfulness"))

    # Benefit: template variables - same rubric definition, new eval dimension.
    # No re-authoring: only the criteria variable changes.
    version, metrics = stage_and_evaluate(
      manager, store, STRICT_RUBRIC, criteria="factual accuracy", label="v3 factual accuracy"
    )
    results.append((version, metrics, "factual accuracy"))

    report_results(store, results)


if __name__ == "__main__":
  main()
