#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
actor="${REUNION_PUBLISH_ACTOR:-unknown}"
note="${REUNION_PUBLISH_NOTE:-}"
lock_file="${REUNION_PUBLISH_LOCK:-/tmp/reunion-publish.lock}"

exec 9>"$lock_file"
if ! flock -n 9; then
  echo "Another reunion publish is already running." >&2
  exit 75
fi

cd "$repo_root"
[[ "$(git rev-parse --abbrev-ref HEAD)" == "master" ]] || { echo "The reunion checkout must be on master." >&2; exit 65; }

git fetch origin master
local_head="$(git rev-parse HEAD)"
remote_head="$(git rev-parse origin/master)"
[[ "$local_head" == "$remote_head" ]] || { echo "The reunion checkout is not synchronized with origin/master. Pull it before publishing." >&2; exit 75; }

unexpected="$(git status --porcelain | awk '$2 != "index.html" {print}')"
[[ -z "$unexpected" ]] || { echo "Unexpected changes in the reunion checkout:" >&2; printf '%s\n' "$unexpected" >&2; exit 65; }

git diff --check -- index.html
if git diff --quiet -- index.html; then
  echo "No reunion page changes to commit."
else
  safe_actor="$(printf '%s' "$actor" | tr -cd '[:alnum:]@._+-' | cut -c1-80)"
  safe_note="$(printf '%s' "$note" | tr '\r\n' '  ' | cut -c1-120)"
  message="Update reunion site from visual editor"
  [[ -n "$safe_note" ]] && message="$message: $safe_note"
  GIT_AUTHOR_NAME="Reunion Web Editor" \
  GIT_AUTHOR_EMAIL="reunion@taylorarchibald.com" \
  GIT_COMMITTER_NAME="Reunion Web Editor" \
  GIT_COMMITTER_EMAIL="reunion@taylorarchibald.com" \
    git add -- index.html
  git commit -m "$message" -m "Published by SSO user: ${safe_actor:-unknown}"
  git push origin master
fi

bash "$repo_root/deploy/deploy.sh" /var/www/taylorarchibald.com/reunion
printf 'Published %s at %s\n' "$(git rev-parse --short HEAD)" "$(date -u +%FT%TZ)"
