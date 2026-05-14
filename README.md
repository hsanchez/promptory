# Promptory

Hardcoded prompt strings are a liability. Enterprise prompt management tools
are too heavy for a fast-moving R&D team. And git alone isn't enough for
production — you need immutable artifacts, explicit configuration, and safety
checks.

Promptory is a Git-based prompt versioning system that gives prompt changes
the same engineering discipline as code: draft, lint, render, version, and
promote.

It tracks the full workflow in Git — file-based and CI-friendly:

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

Requires Python 3.14 or later.

## Install Locally

```bash
uv sync
```

## Use In Another Repo

Install Promptory as a dev dependency in each repo that owns prompts:

```toml
[dependency-groups]
dev = [
  "promptory @ git+https://github.com/hsanchez/promptory.git",
]
```

Then initialize that repo's prompt directory:

```bash
uv sync
uv run prompt init
```

For a full walkthrough, see [the tutorial](docs/tutorial.md).

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
`prompts/promptspec.yaml`. Promptory is the tool that creates release artifacts;
the consuming app reads them.

## Commands

```bash
uv run prompt init
uv run prompt check
uv run prompt draft
uv run prompt release --patch
uv run prompt diff
uv run prompt versions
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
uv run prompt versions
uv run prompt rollback v0.1.0
```

Use draft to restore editable drafts from the active release:

```bash
uv run prompt draft
```

## Concepts

`drafts/` contains editable Jinja templates. Developers and agents work here.

`versions/` contains rendered YAML release artifacts. Promptory creates these
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

`promptspec.yaml` declares the rendered YAML files Promptory manages:

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
from promptory import PromptStore

store = PromptStore("prompts")
system = store.load("system.yaml")
input_guardrail = store.load("input_guardrail.yaml")
output_guardrail = store.load("output_guardrail.yaml")
```

Load a specific release for evals, replay, or debugging:

```python
versions = store.list_versions()
system_v1 = store.load("system.yaml", version="v0.1.0")
prompts_v1 = store.load_all(version="v0.1.0")
```

Use those loaded values when calling your model:

```python
messages = [
  {"role": "system", "content": system["system_prompt"]},
  {"role": "developer", "content": input_guardrail["policy"]},
  {"role": "user", "content": user_message},
]
```

## Prompt Registry Service (`serve`)

To facilitate collaboration across R&D teams (especially those using Go, TypeScript, or other non-Python languages), you can serve your versioned prompts as a REST API.

Install the optional service dependencies:

```toml
[dependency-groups]
dev = [
  "promptory[serve] @ git+https://github.com/hsanchez/promptory.git",
]
```

Start the registry service:

```bash
uv run prompt serve --port 8000
```

The service provides a JSON API for discovery and consumption:

- `GET /versions`: List all available semantic versions.
- `GET /versions/current`: Get the active version string.
- `GET /prompts`: Get all rendered prompts for the current version.
- `GET /prompts/{name}`: Get a specific rendered prompt.
    - Query Param: `?version=v0.1.0` (optional).

## Template Rules

Promptory renders drafts with Jinja `StrictUndefined`, so missing variables fail
instead of becoming empty strings.

Variables using Jinja's `default` filter are optional:

```yaml
model: {{ model | default("gpt-5.5") }}
generated_at: {{ generated_at }}
```

In that template, `generated_at` is required and `model` is optional.

`required_variables` in `promptspec.yaml` declares the variables your templates
are expected to use. `prompt check` reports any template variable not listed
there, and any listed variable that no template references:

```yaml
required_variables:
  - generated_at
```

## Release With Variables From Python

The CLI does not accept release variables yet. Use Python when a draft has
required Jinja variables:

```yaml
# prompts/drafts/prompt.yaml.j2
message: |
  Hello {{ user_name }}, this message has been generated using Jinja2 templating!
  Generated at {{ generation_time }}.
```

```yaml
# prompts/promptspec.yaml
files:
  - prompt.yaml
required_variables:
  - user_name
  - generation_time
max_file_bytes: 100000
```

Release-time code renders the draft into `versions/<version>/prompt.yaml`:

```python
from promptory import PromptStore
from promptory.manager import PromptManager

manager = PromptManager("prompts")
version = manager.release(
  variables={
    "user_name": "Alice",
    "generation_time": "2026-05-09T12:00:00Z",
  }
)

prompt = PromptStore("prompts").load("prompt.yaml", version=version)
print(prompt["message"])
```

`PromptStore` loads rendered YAML. It does not render Jinja at runtime.

## Contributing

Open an issue before sending a pull request for non-trivial changes. All
contributions must pass `uv run prek run --all-files` and `uv run pytest`.

## License

Apache 2.0. See [LICENSE](./LICENSE).

## Citation

Please cite Promptory following the [CITATION.cff](./CITATION.cff) file.
