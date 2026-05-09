# PromptKit

PromptKit is a small Git-based prompt release tool for teams that want prompt
changes to move through drafts, rendered artifacts, and explicit promotion
pointers.

It keeps the workflow file-based:

```text
prompts/
  drafts/
    system.yaml.j2
    input_guardrail.yaml.j2
    output_guardrail.yaml.j2
  versions/
    v0.1.0/
      system.yaml
      input_guardrail.yaml
      output_guardrail.yaml
      metadata.json
  current.json
  promptspec.yaml
```

## Install Locally

```bash
uv sync
```

## Use In Another Repo

Install PromptKit as a dev dependency in each repo that owns prompts:

```toml
[dependency-groups]
dev = [
  "promptkit @ git+ssh://git@github.com/YOUR-ORG/promptkit.git",
]
```

Then initialize that repo's prompt directory:

```bash
uv sync
uv run prompt init
```

The consuming repo keeps the prompt state:

```text
repo/
  prompts/
    drafts/
      system.yaml.j2
      input_guardrail.yaml.j2
      output_guardrail.yaml.j2
    versions/
      v0.1.0/
        system.yaml
        input_guardrail.yaml
        output_guardrail.yaml
        metadata.json
    current.json
    promptspec.yaml
```

Commit `prompts/drafts/`, `prompts/versions/`, `prompts/current.json`, and
`prompts/promptspec.yaml`. PromptKit is the tool that creates release artifacts;
the consuming app reads them.

## Commands

```bash
uv run prompt init
uv run prompt check
uv run prompt draft
uv run prompt release --patch
uv run prompt diff
uv run prompt rollback v0.1.0
```

Typical workflow:

```bash
uv run prompt check
uv run prompt diff
uv run prompt release --patch
```

Use rollback to point `current.json` at an existing release:

```bash
uv run prompt rollback v0.1.0
```

Use draft to restore editable drafts from the active release:

```bash
uv run prompt draft
```

## Model

`drafts/` contains editable Jinja templates. Developers and agents work here.

`versions/` contains rendered YAML release artifacts. PromptKit creates these
directories. Treat them as immutable after creation.

`current.json` points at the active release. Rollback updates this pointer.

Example:

```json
{
  "version": "v0.1.0",
  "updated_at": "2026-05-09T22:14:00.000000+00:00"
}
```

Applications and CI read `current.json`, then load rendered YAML files from
`versions/<version>/`.

`promptspec.yaml` declares the rendered YAML files PromptKit manages:

```yaml
files:
  - system.yaml
  - input_guardrail.yaml
  - output_guardrail.yaml
required_variables: []
max_file_bytes: 100000
```

Prompt files must be relative `.yaml` paths. Draft templates use the same path
with `.j2` appended, so `system.yaml` renders from `system.yaml.j2`.

## Use Released Prompts In An App

Applications should read rendered prompts from the active version. Do not load
files from `drafts/` at runtime. Use `PromptStore` to load only files declared
in `promptspec.yaml` from the active release.

```python
from promptkit import PromptStore

store = PromptStore("prompts")
system = store.load("system.yaml")
input_guardrail = store.load("input_guardrail.yaml")
output_guardrail = store.load("output_guardrail.yaml")
```

Use those loaded values when calling your model:

```python
messages = [
  {"role": "system", "content": system["system_prompt"]},
  {"role": "developer", "content": input_guardrail["policy"]},
  {"role": "user", "content": user_message},
]
```

## Template Rules

PromptKit renders drafts with Jinja `StrictUndefined`, so missing variables fail
instead of becoming empty strings.

Variables using Jinja's `default` filter are optional:

```yaml
model: {{ model | default("gpt-5.5") }}
generated_at: {{ generated_at }}
```

In that template, `generated_at` is required and `model` is optional.

List required variables in `promptspec.yaml` so `prompt check` can catch
unexpected template inputs:

```yaml
required_variables:
  - generated_at
```
