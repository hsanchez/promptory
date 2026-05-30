# FAQ

## Why not just use Git?

Git records changes, but production prompt workflows also need rendered release
artifacts, metadata, checksums, and a clear pointer to the active version.

## What is the difference between drafts and versions?

`drafts/` contains editable Jinja templates. `versions/` contains rendered YAML
artifacts created by Promptory.

## Are versions editable?

No. Treat each directory under `versions/` as immutable after creation. Make a
new draft change and release a new version instead.

## What is a staged release?

A staged release is a rendered version under `versions/` that is not active yet.
Create one with:

```bash
uv run prompt release --patch --staged
```

Promote it when it is ready:

```bash
uv run prompt promote v0.1.0
```

Promotion updates `current.json`.

## What is release evidence?

Evidence is immutable metadata attached to a release. External tools produce it;
Promptory stores it with the exact rendered version it describes.

```bash
uv run prompt evidence add v0.1.0 eval-results.json
uv run prompt evidence list v0.1.0
uv run prompt evidence show v0.1.0 customer-support-regression
```

Promptory validates the basic evidence shape but does not run evals, call LLMs,
manage datasets, or define metric semantics.

## How do I compare evidence between releases?

Use:

```bash
uv run prompt evidence compare v0.1.0 v0.2.0
```

Promptory compares attached evidence by `kind` and `name`, then shows status,
revocation, and simple scalar metric changes. It does not decide whether one
prompt is better.

## How do I summarize prompt changes?

Use:

```bash
uv run prompt diff --summary
```

Compare two released versions:

```bash
uv run prompt diff --summary --from v0.1.0 --to v0.2.0
```

The summary shows changed managed files, character count deltas, and scalar YAML
value changes. Use `prompt diff` for the full unified diff.

## How do I use Promptory in CI?

Use `--format json` for machine-readable output and `--format markdown` for job
summaries:

```bash
uv run prompt diff --summary --format json
uv run prompt evidence list v0.1.0 --format json
uv run prompt evidence compare v0.1.0 v0.2.0 --format markdown
```

Use GitHub annotations for release gates:

```bash
uv run prompt gate v0.1.0 --format github
```

`prompt gate` still exits non-zero when gates fail.

## What are release gates?

Release gates are promotion requirements declared in `promptspec.yaml`.

```yaml
release_gates:
  evidence:
    - kind: eval
      name: customer-support-regression
      required_status: pass
```

Check a version:

```bash
uv run prompt gate v0.1.0
```

Require passing gates during promotion:

```bash
uv run prompt promote v0.1.0 --require-gates
```

Promptory checks attached evidence. It does not run evals or safety checks.

## Can evidence be removed?

No. Evidence is immutable. Revoke invalid evidence instead:

```bash
uv run prompt evidence revoke v0.1.0 customer-support-regression \
  --reason "Eval used stale fixtures."
```

Revocation records a new artifact and lifecycle event. It does not edit or delete
the original evidence file.

## Why is the directory named versions instead of .vault?

Release artifacts are part of the project state users should review and commit.
A visible `versions/` directory makes that workflow explicit.

## Does Promptory store templates or rendered prompts?

Drafts are templates. Versions are rendered YAML prompts.

## What prompt file types are supported?

Managed prompt files are `.yaml` files. Each declared file has a matching draft
template with `.j2` appended, such as `system.yaml.j2`.

## Can I track multiple prompts?

Yes. Add each rendered `.yaml` file to `promptspec.yaml`:

```yaml
files:
  - system.yaml
  - input_guardrail.yaml
  - output_guardrail.yaml
```

Promptory renders each matching draft template into the same release directory.

## How are Jinja variables handled?

Promptory renders with Jinja `StrictUndefined`. Missing variables fail instead
of rendering as empty strings.

## Are Jinja defaults considered required variables?

No. Variables that use the `default` filter are optional. Other undeclared
variables must be listed in `required_variables` and supplied by the caller.

## Can runtime code pass variables into prompts?

No. Runtime code uses `PromptStore`, which loads rendered YAML from a release.
It does not render Jinja.

Use `PromptManager.release(variables=...)` before runtime:

```python
from promptory.manager import PromptManager

version = PromptManager("prompts").release(
  variables={
    "user_name": "Alice",
    "generation_time": "2026-05-09T12:00:00Z",
  }
)
```

The CLI does not accept release variables yet.

## How does rollback work?

Rollback updates `current.json` to point at an existing release. It does not
rewrite files inside `versions/`.

## Does draft restore evidence?

No. Draft recovery copies prompt text from the current release back to
`drafts/`. Evidence remains attached to the release it describes.

## How does my app use released prompts?

Use `PromptStore`:

```python
from promptory import PromptStore

store = PromptStore("prompts")
system = store.load("system.yaml")
```

`PromptStore` reads `current.json`, loads rendered YAML from
`versions/<version>/`, and rejects files not declared in `promptspec.yaml`.

## Can my app load a specific prompt version?

Yes. Pass `version` to `PromptStore`:

```python
versions = store.list_versions()
system = store.load("system.yaml", version="v0.1.0")
prompts = store.load_all(version="v0.1.0")
```

Omit `version` to load the active release from `current.json`.

## How do I see available prompt versions?

Use the CLI:

```bash
uv run prompt versions
```

Or use `PromptStore`:

```python
versions = store.list_versions()
```

## Can I use curl with the sidecar adapter?

Yes. Start the service:

```bash
uv run prompt serve --port 8000
```

Then call the JSON endpoints:

```bash
curl http://localhost:8000/versions
curl http://localhost:8000/versions/current
curl http://localhost:8000/prompts
curl http://localhost:8000/prompts/system.yaml
curl "http://localhost:8000/prompts/system.yaml?version=v0.1.0"
```

Use `python -m json.tool` for readable output:

```bash
curl -s http://localhost:8000/prompts | python -m json.tool
```

## Should my app read from drafts?

No. `drafts/` can contain unrendered Jinja variables and work-in-progress
changes. Runtime code should read `versions/<version>/`.

## Should generated versions be committed?

Yes. Commit `promptspec.yaml`, `drafts/`, `versions/`, and `current.json` so code
review and CI can inspect the exact prompt artifacts.

## When should I use a hosted prompt platform instead?

Use a hosted prompt platform when non-technical users need a UI, many teams need
shared governance, or prompt metadata no longer fits a repository workflow.
