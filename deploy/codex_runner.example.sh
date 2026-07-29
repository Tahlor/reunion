#!/usr/bin/env bash
set -euo pipefail

# Host runner for REUNION_CODEX_RUNNER.
#
# The service invokes this fixed executable and sends exactly one user message
# on stdin. Browser text is data: it is never evaluated as a shell command or
# used to select an executable. The first call creates a Codex session and
# records its thread id; later calls resume that same session.

: "${REUNION_REPO_ROOT:?}"
: "${REUNION_CODEX_SESSION_DIR:?}"

repo_root="$(cd -- "$REUNION_REPO_ROOT" && pwd -P)"
[[ -d "$repo_root/.git" ]] || { echo "Reunion repository is not a Git checkout." >&2; exit 65; }
cd "$repo_root"

prompt="$(cat)"
[[ -n "$prompt" ]] || { echo "Empty prompt" >&2; exit 64; }

session_root="$(cd -- "$REUNION_CODEX_SESSION_DIR" && pwd -P 2>/dev/null || true)"
if [[ -z "$session_root" || ! -d "$session_root" ]]; then
  mkdir -p "$REUNION_CODEX_SESSION_DIR"
  session_root="$(cd -- "$REUNION_CODEX_SESSION_DIR" && pwd -P)"
fi
chmod 700 "$session_root"

# Keeping CODEX_HOME in the private reunion data root ensures the durable
# session files do not land in the public document root or the repository.
export CODEX_HOME="${REUNION_CODEX_HOME:-$session_root}"
mkdir -p "$CODEX_HOME"
chmod 700 "$CODEX_HOME"

codex_bin="/home/ubuntu/.npm-global/bin/codex"
[[ -x "$codex_bin" ]] || codex_bin="/usr/local/bin/codex"
[[ -x "$codex_bin" ]] || { echo "The installed Codex executable was not found." >&2; exit 69; }

session_file="$session_root/reunion-session-id"
events_file="$(mktemp "$session_root/events.XXXXXX")"
message_file="$(mktemp "$session_root/message.XXXXXX")"
error_file="$(mktemp "$session_root/error.XXXXXX")"
trap 'rm -f "$events_file" "$message_file" "$error_file"' EXIT
chmod 600 "$events_file" "$message_file" "$error_file"

if [[ -s "$session_file" ]]; then
  session_id="$(head -n 1 "$session_file")"
  set +e
  "$codex_bin" exec resume --json --dangerously-bypass-approvals-and-sandbox \
    -o "$message_file" "$session_id" - < <(printf '%s' "$prompt") >"$events_file" 2>"$error_file"
  command_status=$?
  set -e
else
  set +e
  "$codex_bin" exec --json --color never --dangerously-bypass-approvals-and-sandbox \
    -C "$repo_root" -o "$message_file" - < <(printf '%s' "$prompt") >"$events_file" 2>"$error_file"
  command_status=$?
  set -e
fi

thread_id="$(python3 - "$events_file" <<'PY'
import json
import sys

def find_id(value):
    if not isinstance(value, dict):
        return ""
    for key in ("thread_id", "threadId"):
        if value.get(key):
            return str(value[key])
    thread = value.get("thread")
    if isinstance(thread, dict) and thread.get("id"):
        return str(thread["id"])
    params = value.get("params")
    if isinstance(params, dict):
        found = find_id(params)
        if found:
            return found
    return ""

for line in open(sys.argv[1], encoding="utf-8", errors="replace"):
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        continue
    found = find_id(event)
    if found:
        print(found)
        break
PY
)"
if [[ -n "${thread_id:-}" && ! -s "$session_file" ]]; then
  umask 077
  printf '%s\n' "$thread_id" > "$session_file"
fi

if [[ -s "$message_file" ]]; then
  cat "$message_file"
else
  # Older/newer CLI builds can omit --output-last-message content in JSON
  # mode. Recover the final assistant message from the JSONL event stream.
  python3 - "$events_file" <<'PY'
import json
import sys

parts = []
for line in open(sys.argv[1], encoding="utf-8", errors="replace"):
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        continue
    item = event.get("item") if isinstance(event, dict) else None
    if isinstance(item, dict) and item.get("type") == "agentMessage" and item.get("text"):
        parts.append(str(item["text"]))
    if event.get("type") in {"response.output_text.delta", "item/agentMessage/delta"} and event.get("delta"):
        parts.append(str(event["delta"]))
if parts:
    print(parts[-1] if len(parts) == 1 else "".join(parts))
PY
fi

if [[ -s "$error_file" ]]; then
  cat "$error_file" >&2
fi
exit "$command_status"
