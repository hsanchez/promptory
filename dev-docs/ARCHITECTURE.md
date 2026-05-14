# Architecture

Promptory manages prompt lifecycle state on the filesystem. Git remains the
source of history, while Promptory creates release artifacts with explicit
metadata and a current-release pointer.

## Component Map

```mermaid
flowchart TD
  Developer[Developer] --> Drafts[drafts/*.yaml.j2]
  Developer --> CLI[prompt CLI]

  CLI --> Manager[PromptManager]
  CLI --> Store[PromptStore]
  CLI --> Service[prompt serve]

  Manager --> Spec[promptspec.yaml loader]
  Manager --> Linter[Prompt linter]
  Manager --> Renderer[Jinja renderer]
  Manager --> Release[Release writer]
  Manager --> Diff[Diff engine]

  Linter --> Drafts
  Renderer --> Drafts
  Renderer --> YAML[YAML parser]
  Release --> Versions[versions/vX.Y.Z]
  Release --> Current[current.json]
  Diff --> Drafts
  Diff --> Versions

  App[Python application] --> Store
  HTTP[Non-Python client] --> Service
  Service --> Store
  Store --> Spec
  Store --> Current
  Store --> Versions
```

The core boundary is file-based. Authoring tools write `drafts/`, `versions/`,
and `current.json`; runtime tools read `promptspec.yaml`, `current.json`, and
`versions/`.

## Components

### PromptManager

`PromptManager` is the high-level authoring API. It owns project initialization,
draft recovery from the current release, prompt checks, release creation, diffs,
and rollback.

Responsibilities:

- Create the prompt directory layout and default `promptspec.yaml`.
- Load the prompt specification before authoring operations.
- Run checks before releases through the linter.
- Create immutable releases through the release writer.
- Point `current.json` at an existing release during rollback.

`PromptManager` is allowed to write prompt lifecycle files. Runtime application
code should use `PromptStore` instead.

### PromptSpec Loader

The spec loader reads `promptspec.yaml` and returns a validated `PromptSpec`.
`PromptSpec` is the shared configuration object for authoring and runtime code.

Responsibilities:

- Validate managed prompt file names.
- Expose derived paths for `drafts/`, `versions/`, `current.json`, and
  `promptspec.yaml`.
- Validate `required_variables` and `max_file_bytes`.

### Prompt Linter

The linter validates drafts before release. It checks the declared prompt set,
template syntax, file size limits, required-variable declarations, and static YAML
where possible.

The linter returns user-facing errors instead of raising for normal validation
failures. The CLI prints those errors and exits non-zero.

### Renderer

The renderer turns declared Jinja draft templates into rendered YAML strings.

Responsibilities:

- Map each managed `*.yaml` file to a `drafts/*.yaml.j2` template.
- Render with Jinja `StrictUndefined`.
- Treat variables using Jinja `default` filters as optional during validation.
- Parse rendered YAML before release artifacts are written.

Rendering happens only during authoring and release. Runtime loading never
renders Jinja.

### Release Writer

The release writer owns semantic version discovery, version normalization,
version bumps, release directory creation, `metadata.json`, and `current.json`.

Responsibilities:

- List valid semantic release directories.
- Normalize versions to the `vX.Y.Z` form.
- Render drafts before writing a release.
- Write rendered YAML files and release metadata.
- Update the current-release pointer.
- Remove a partially-created release directory if writing fails.

### PromptStore

`PromptStore` is the runtime API for Python consumers. It reads released prompt
artifacts and never reads draft templates.

Responsibilities:

- Resolve the active release from `current.json`.
- List available semantic release directories.
- Validate requested prompt names against `promptspec.yaml`.
- Load one declared prompt or all declared prompts.
- Load either the active release or an explicit release version.

`PromptStore` returns parsed YAML mappings so applications can pass loaded values
to their LLM provider or internal prompt layer.

### Prompt CLI

The `prompt` CLI is a thin user interface over `PromptManager`, `PromptStore`,
and the registry service launcher.

Responsibilities:

- Run authoring commands: `init`, `draft`, `check`, `release`, `diff`, and
  `rollback`.
- List release versions through `PromptStore`.
- Start the optional registry service with `prompt serve`.

### Registry Service

The registry service is a FastAPI wrapper around `PromptStore` for non-Python
consumers. It exposes released prompts over HTTP without adding a second prompt
lifecycle.

Responsibilities:

- Read the prompts directory from `PROMPTORY_PROMPTS_DIR`.
- Return service metadata, versions, current version, all prompts, or one prompt.
- Map Promptory exceptions to HTTP errors.
- Preserve the read-only runtime boundary.

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

## Authoring Flow

```mermaid
sequenceDiagram
  actor Developer
  participant CLI as prompt CLI
  participant Manager as PromptManager
  participant Spec as PromptSpec loader
  participant Linter as Prompt linter
  participant Renderer as Renderer
  participant Release as Release writer
  participant Files as prompts/

  Developer->>CLI: prompt release
  CLI->>Manager: check()
  Manager->>Spec: load promptspec.yaml
  Manager->>Linter: lint drafts
  Linter->>Files: read drafts/*.yaml.j2
  CLI->>Manager: release()
  Manager->>Release: create release
  Release->>Renderer: render declared drafts
  Renderer->>Files: read drafts/*.yaml.j2
  Renderer-->>Release: rendered YAML
  Release->>Files: write versions/vX.Y.Z
  Release->>Files: write metadata.json
  Release->>Files: update current.json
```

Authoring commands can inspect or mutate lifecycle state. Git remains the durable
history for source changes, while Promptory writes release artifacts for runtime
consumers.

## Runtime Flow

```mermaid
sequenceDiagram
  participant App as Application
  participant Store as PromptStore
  participant Spec as PromptSpec loader
  participant Files as prompts/

  App->>Store: load("system.yaml")
  Store->>Spec: load promptspec.yaml
  Store->>Files: read current.json
  Store->>Files: read versions/current/system.yaml
  Store-->>App: parsed YAML mapping
```

Runtime loading is intentionally smaller than release creation. It validates the
requested file against `promptspec.yaml`, resolves the active or explicit
version, and loads rendered YAML from a known release directory.

## Invariants

- `promptspec.yaml` is the only source for managed prompt file names.
- Managed prompt files are relative `.yaml` paths.
- Absolute paths, parent traversal, duplicate files, non-YAML files, and
  `metadata.json` are invalid.
- Draft templates render with Jinja `StrictUndefined`.
- Variables with Jinja `default` filters are optional.
- Non-default Jinja variables must be listed in `required_variables`.
- Release artifacts are rendered YAML and must parse successfully before release.
- Promptory writes `versions/` and `current.json`; developers edit `drafts/`.
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

If writing the release fails, Promptory removes the partially-created release
directory.

## Boundaries

Promptory does not deploy prompts. CI/CD, applications, or provider-specific
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

```mermaid
sequenceDiagram
  participant Client as HTTP client
  participant API as FastAPI service
  participant Store as PromptStore
  participant Files as prompts/

  Client->>API: GET /prompts/system.yaml
  API->>Store: load("system.yaml")
  Store->>Files: read promptspec.yaml
  Store->>Files: read current.json
  Store->>Files: read versions/current/system.yaml
  Store-->>API: parsed YAML mapping
  API-->>Client: JSON response
```

`prompt serve` starts an optional FastAPI service for non-Python consumers. The
service is a read-only HTTP wrapper around `PromptStore`; it does not render
drafts, create releases, mutate `current.json`, or deploy prompts.

The server dependencies live behind the `serve` extra:

```toml
promptory[serve]
```

The prompts directory is configured with `PROMPTORY_PROMPTS_DIR`. The CLI sets
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
