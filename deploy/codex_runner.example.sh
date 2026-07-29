#!/usr/bin/env bash
set -euo pipefail

# Contract for REUNION_CODEX_RUNNER:
#   * Read one user message from stdin.
#   * Work only in $REUNION_REPO_ROOT.
#   * Persist/resume one Codex conversation in $REUNION_CODEX_SESSION_DIR.
#   * Print the assistant-facing response to stdout.
#   * Return non-zero and put diagnostic details on stderr on failure.
#   * Never accept a shell command from the browser.
#
# The Archimedes agent must replace this example with a host-specific wrapper
# after checking the installed Codex CLI/SDK version. Prefer reusing the existing
# webapps/codex_apps session machinery when it can bind a durable session to this
# fixed repository. Otherwise use the supported Codex SDK/CLI session interface.

: "${REUNION_REPO_ROOT:?}"
: "${REUNION_CODEX_SESSION_DIR:?}"
cd "$REUNION_REPO_ROOT"
prompt="$(cat)"
[[ -n "$prompt" ]] || { echo "Empty prompt" >&2; exit 64; }

echo "Codex runner is not configured. Wire this wrapper to the installed Codex CLI/SDK on Archimedes." >&2
exit 78
