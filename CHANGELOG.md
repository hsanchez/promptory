# Changelog

## Unreleased

### Added

- Added staged releases with `prompt release --staged` and `prompt promote`.
- Added immutable release evidence with `prompt evidence add`, `list`, `show`, and `revoke`.
- Added evidence comparison with `prompt evidence compare`.
- Added semantic prompt diff summaries with `prompt diff --summary`.
- Added CI-friendly `--format` output for release gates, diff summaries, and evidence commands.
- Added append-only release lifecycle history in `lifecycle.jsonl`.
- Added release gates with `prompt gate` and `prompt promote --require-gates`.
- Added `release_gates` configuration in `promptspec.yaml`.
