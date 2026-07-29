#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
destination="${1:-/var/www/taylorarchibald.com/reunion}"

if ! command -v rsync >/dev/null 2>&1; then
  echo "rsync is required" >&2
  exit 1
fi

sudo install -d -m 0755 -o www-data -g www-data "$destination"
sudo rsync -a --delete \
  --exclude '.git/' \
  --exclude '.venv/' \
  --exclude 'server/' \
  --exclude 'deploy/' \
  --exclude 'README.md' \
  --exclude 'AGENTS.md' \
  "$repo_root/" "$destination/"
sudo chown -R www-data:www-data "$destination"
sudo find "$destination" -type d -exec chmod 0755 {} +
sudo find "$destination" -type f -exec chmod 0644 {} +

echo "Deployed Hazard reunion site to $destination"
