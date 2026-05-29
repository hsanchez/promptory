# Tutorial

This tutorial walks through using Promptory from another repository. It follows
the same workflow used in the local smoke test: install Promptory, create prompt
drafts, release rendered YAML artifacts, and load them from application code.

## Prerequisites

- Python 3.14 or later
- `uv`
- A repository that owns prompt files

## Create A Demo App

Create a new project:

```bash
mkdir promptory-demo
cd promptory-demo
uv init --bare
```

Add Promptory as a dependency:

```toml
# pyproject.toml
[project]
name = "promptory-demo"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = [
  "promptory @ git+https://github.com/hsanchez/promptory.git",
]
```

Then install dependencies:

```bash
uv sync
```

If you use GitHub SSH locally, this dependency also works:

```toml
"promptory @ git+ssh://git@github.com/hsanchez/promptory.git"
```

## Initialize Promptory

Create the prompt directory:

```bash
uv run prompt init
```

Promptory creates:

```text
prompts/
  drafts/
    system.yaml.j2
  versions/
  promptspec.yaml
```

The default draft is editable:

```yaml
# prompts/drafts/system.yaml.j2
model: gpt-5.5
temperature: 0.2
system_prompt: |
  You are a helpful assistant.
```

The default spec declares the rendered YAML file:

```yaml
# prompts/promptspec.yaml
files:
- system.yaml
required_variables: []
max_file_bytes: 100000
```

## Check And Release

Validate the drafts:

```bash
uv run prompt check
```

Create the first release:

```bash
uv run prompt release --patch
```

Promptory writes:

```text
prompts/
  versions/
    v0.0.1/
      system.yaml
      metadata.json
      lifecycle.jsonl
      evidence/
  current.json
```

`current.json` points at the active release:

```json
{
  "version": "v0.0.1",
  "updated_at": "2026-05-09T22:14:00.000000+00:00"
}
```

List available releases:

```bash
uv run prompt versions
```

Output:

```text
v0.0.1
```

## Stage A Release Before Promotion

Use a staged release when external checks need to inspect a rendered version
before it becomes active:

```bash
uv run prompt release --patch --staged
```

Promptory writes the new version under `prompts/versions/`, but leaves
`current.json` unchanged.

Attach evidence produced by an external tool:

```bash
uv run prompt evidence add v0.0.2 customer-support-regression.json
```

Evidence documents use a small schema:

```json
{
  "kind": "eval",
  "name": "customer-support-regression",
  "status": "pass",
  "tool": "internal-eval-runner",
  "created_at": "2026-05-24T12:00:00Z",
  "summary": "No regressions against billing and refund scenarios.",
  "metrics": {
    "pass_rate": 0.94,
    "failed_cases": 3
  }
}
```

Review evidence:

```bash
uv run prompt evidence list v0.0.2
uv run prompt evidence show v0.0.2 customer-support-regression
```

Compare evidence with another release:

```bash
uv run prompt evidence compare v0.0.1 v0.0.2
```

Summarize prompt changes at a higher level:

```bash
uv run prompt diff --summary
uv run prompt diff --summary --from v0.0.1 --to v0.0.2
```

If evidence is invalid, revoke it. Promptory records revocation without deleting
the original evidence:

```bash
uv run prompt evidence revoke v0.0.2 customer-support-regression \
  --reason "Eval used stale fixtures."
```

Configure release gates when promotion should require specific evidence:

```yaml
# prompts/promptspec.yaml
release_gates:
  evidence:
    - kind: eval
      name: customer-support-regression
      required_status: pass
```

Check gates before promotion:

```bash
uv run prompt gate v0.0.2
```

Promote the staged release when it is ready:

```bash
uv run prompt promote v0.0.2 --require-gates
```

Promotion updates `current.json`.

## Load Prompts In Application Code

Create `demo_app.py`:

```python
from promptory import PromptStore


def main() -> None:
  store = PromptStore("prompts")
  system = store.load("system.yaml")

  print(f"Current version: {store.current_version()}")
  print(f"Available versions: {store.list_versions()}")
  print(system["system_prompt"])


if __name__ == "__main__":
  main()
```

Run it:

```bash
uv run python demo_app.py
```

Application code reads rendered YAML from `prompts/versions/<version>/`.
It does not read from `prompts/drafts/`.

## Add More Prompt Files

Promptory can track multiple rendered YAML files in the same release.

Update `prompts/promptspec.yaml`:

```yaml
files:
- system.yaml
- input_guardrail.yaml
- output_guardrail.yaml
required_variables: []
max_file_bytes: 100000
```

Add draft templates:

```yaml
# prompts/drafts/input_guardrail.yaml.j2
policy: |
  Reject requests for secrets, credentials, or private keys.
```

```yaml
# prompts/drafts/output_guardrail.yaml.j2
policy: |
  Answer concisely and avoid unsupported claims.
```

Check the drafts:

```bash
uv run prompt check
```

Preview the changes:

```bash
uv run prompt diff
```

Create the next release:

```bash
uv run prompt release --patch
```

Promptory writes:

```text
prompts/
  versions/
    v0.0.2/
      system.yaml
      input_guardrail.yaml
      output_guardrail.yaml
      metadata.json
```

Update `demo_app.py`:

```python
from promptory import PromptStore


def main() -> None:
  store = PromptStore("prompts")

  system = store.load("system.yaml")
  input_guardrail = store.load("input_guardrail.yaml")
  output_guardrail = store.load("output_guardrail.yaml")

  print(f"Current version: {store.current_version()}")
  print(f"Available versions: {store.list_versions()}")
  print(system["system_prompt"])
  print(input_guardrail["policy"])
  print(output_guardrail["policy"])


if __name__ == "__main__":
  main()
```

Run it:

```bash
uv run python demo_app.py
```

## Load A Specific Version

`PromptStore` loads the active release by default. Pass `version` to load a
specific release:

```python
from promptory import PromptStore

store = PromptStore("prompts")
system_v1 = store.load("system.yaml", version="v0.0.1")
all_v2 = store.load_all(version="v0.0.2")
```

This is useful for evals, replay, and debugging.

## Roll Back

Rollback updates `current.json` to point at an existing release. It does not
delete or rewrite release files.

```bash
uv run prompt versions
uv run prompt rollback v0.0.1
```

After rollback, application code that calls `store.load("system.yaml")` reads
from `v0.0.1`.

## Release With Variables

Promptory drafts are Jinja templates. Variables are rendered at release time,
not runtime.

Example draft:

```yaml
# prompts/drafts/prompt.yaml.j2
message: |
  Hello {{ user_name }}, this message has been generated using Jinja2 templating!
  Generated at {{ generation_time }}.
```

Spec:

```yaml
files:
- prompt.yaml
required_variables:
- user_name
- generation_time
max_file_bytes: 100000
```

Release from Python:

```python
from promptory.manager import PromptManager

version = PromptManager("prompts").release(
  variables={
    "user_name": "Alice",
    "generation_time": "2026-05-09T12:00:00Z",
  }
)
```

Then load the rendered prompt:

```python
from promptory import PromptStore

prompt = PromptStore("prompts").load("prompt.yaml", version=version)
print(prompt["message"])
```

The CLI does not accept release variables yet.

## What To Commit

Commit these files in the consuming repository:

```text
prompts/drafts/
prompts/versions/
prompts/current.json
prompts/promptspec.yaml
```

Treat `prompts/versions/` as generated and immutable. Edit drafts, then create a
new release.
