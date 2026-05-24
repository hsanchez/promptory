#!/usr/bin/env bash
# Sidecar adapter demo.
#
# Shows how a non-Python service consumes prompts over HTTP while the Python
# team manages the prompt lifecycle with Promptory.
#
# Prerequisites:
#   uv sync  (installs promptory[serve])
#
# Run from the repo root:
#   bash examples/sidecar.sh

set -euo pipefail

PROMPTS_DIR="$(mktemp -d)/prompts"
PORT=18432  # high port to avoid conflicts
SERVE_PID=""

cleanup() {
  if [[ -n "$SERVE_PID" ]]; then
    kill "$SERVE_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

wait_for_sidecar() {
  for _ in {1..30}; do
    if curl -sf "http://localhost:$PORT/" >/dev/null; then
      return 0
    fi
    sleep 0.2
  done

  echo "Sidecar did not become ready on port $PORT" >&2
  return 1
}

echo "=== init ==="
uv run prompt init --prompts-dir "$PROMPTS_DIR"

# Write a draft with no variables so it releases without extra arguments.
cat > "$PROMPTS_DIR/drafts/system.yaml.j2" <<'DRAFT'
model: gpt-5.5
temperature: 0.2
system_prompt: |
  You are a helpful assistant.
DRAFT

echo "=== release v0.0.1 ==="
uv run prompt release --patch --prompts-dir "$PROMPTS_DIR"

echo "=== start sidecar ==="
# The sidecar runs alongside the service that owns this prompt repo.
# It reads current.json on every request, so new releases are visible
# immediately without a restart.
uv run prompt serve --prompts-dir "$PROMPTS_DIR" --port "$PORT" &
SERVE_PID=$!
wait_for_sidecar

echo "=== non-Python consumer: curl ==="
curl -sf "http://localhost:$PORT/versions/current"
echo
curl -sf "http://localhost:$PORT/prompts/system.yaml"
echo

echo "=== release v0.0.2 (no sidecar restart) ==="
cat > "$PROMPTS_DIR/drafts/system.yaml.j2" <<'DRAFT'
model: gpt-5.5
temperature: 0.1
system_prompt: |
  You are a concise assistant.
DRAFT
uv run prompt release --patch --prompts-dir "$PROMPTS_DIR"

echo "=== curl sees new version immediately ==="
curl -sf "http://localhost:$PORT/versions/current"
echo
curl -sf "http://localhost:$PORT/prompts/system.yaml"
echo

echo "=== fetch a specific version for evals ==="
curl -sf "http://localhost:$PORT/prompts/system.yaml?version=v0.0.1"
echo

echo "=== done ==="
