# Architecture

PromptKit manages prompt lifecycle state on the filesystem. Git remains the
source of history, while PromptKit creates release artifacts with explicit
metadata and a current-release pointer.

## Directories

```text
prompts/
  drafts/
  versions/
  current.json
  promptspec.yaml
```

`drafts/` contains editable Jinja templates. Every managed prompt is YAML, so a
declared file such as `system.yaml` maps to `drafts/system.yaml.j2`.

`versions/` contains immutable rendered artifacts. A release directory is named
with a normalized semantic version such as `v0.1.0` and contains rendered YAML
plus `metadata.json`.

`current.json` points at the active release. Rollback changes the pointer instead
of rewriting prompt artifacts.

A project can track one prompt file or many prompt files. Every entry in
`promptspec.yaml` maps to one draft template and one rendered release artifact.

## Invariants

- `promptspec.yaml` is the only source for managed prompt file names.
- Managed prompt files are relative `.yaml` paths.
- Absolute paths, parent traversal, duplicate files, non-YAML files, and
  `metadata.json` are invalid.
- Draft templates render with Jinja `StrictUndefined`.
- Variables with Jinja `default` filters are optional.
- Non-default Jinja variables must be listed in `required_variables`.
- Release artifacts are rendered YAML and must parse successfully before release.
- PromptKit writes `versions/` and `current.json`; developers edit `drafts/`.
- Runtime code reads `current.json` and `versions/<version>/`; runtime code does
  not read `drafts/`.

## Release Flow

1. Load and validate `promptspec.yaml`.
2. Render every draft template with Jinja.
3. Validate rendered YAML.
4. Create the next semantic version directory under `versions/`.
5. Write rendered YAML files and `metadata.json`.
6. Update `current.json` to point at the new release.

Release-time variables flow through `PromptManager.release(variables=...)`.
Rendered releases contain resolved YAML; runtime loading does not render Jinja.

If writing the release fails, PromptKit removes the partially-created release
directory.

## Boundaries

PromptKit does not deploy prompts. CI/CD, applications, or provider-specific
tools consume `current.json` and `versions/`.

The runtime contract is:

1. Create `PromptStore("prompts")`.
2. Resolve the active version with `current_version()` when needed.
3. List available releases with `list_versions()`.
4. Load active rendered YAML with `load(file_name)` or `load_all()`.
5. Load a specific release with `load(file_name, version="v0.1.0")` or
   `load_all(version="v0.1.0")`.
6. Pass the loaded values to the LLM provider or application code.

`PromptStore` validates file names against `promptspec.yaml`, reads
`current.json` for active loads, normalizes explicit versions, and loads YAML
only from known release directories. Release listings include valid semantic
version directories sorted by semantic version.

Future deployment integrations should live outside the core release path unless
they preserve the same file-based artifacts and pointer model.

## Registry Service

`prompt serve` starts an optional FastAPI service for non-Python consumers. The
service is a read-only HTTP wrapper around `PromptStore`; it does not render
drafts, create releases, mutate `current.json`, or deploy prompts.

The server dependencies live behind the `serve` extra:

```toml
promptkit[serve]
```

The prompts directory is configured with `PROMPTKIT_PROMPTS_DIR`. The CLI sets
this environment variable from `--prompts-dir` before launching Uvicorn.

Endpoints:

- `GET /` returns service metadata.
- `GET /versions` lists valid semantic release directories.
- `GET /versions/current` returns the active version from `current.json`.
- `GET /prompts` returns all rendered prompts for the active or requested
  version.
- `GET /prompts/{name:path}` returns one rendered prompt, including nested
  prompt paths such as `agents/support/system.yaml`.

The service maps `PromptLoadError` to 404 and prompt specification errors to
client or server errors depending on whether the request supplied invalid prompt
input or the repository configuration is invalid.
