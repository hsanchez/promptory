# PromptKit

PromptKit is a small Git-based prompt release tool for teams that want prompt
changes to move through drafts, rendered artifacts, and explicit promotion
pointers.

It keeps the workflow file-based:

```text
prompts/
  drafts/
    system.yaml.j2
  versions/
    v0.1.0/
      system.yaml
      metadata.json
  current.json
  promptspec.yaml
```

## Install Locally

```bash
uv sync
```

## Commands

```bash
uv run prompt init
uv run prompt draft
uv run prompt check
uv run prompt release --patch
uv run prompt diff
uv run prompt rollback v0.1.0
```

## Model

`drafts/` contains editable Jinja templates. Developers and agents work here.

`versions/` contains rendered YAML release artifacts. PromptKit creates these
directories. Treat them as immutable after creation.

`current.json` points at the active release. Rollback updates this pointer.

`promptspec.yaml` declares the rendered YAML files PromptKit manages:

```yaml
files:
  - system.yaml
required_variables: []
max_file_bytes: 100000
```

Prompt files must be relative `.yaml` paths. Draft templates use the same path
with `.j2` appended, so `system.yaml` renders from `system.yaml.j2`.

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
