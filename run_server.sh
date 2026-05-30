#!/bin/bash
# Wrapper that sources .env and launches server.py.
# Used by the launchd LaunchAgent so secrets (GOOGLE_MAPS_KEY) stay in .env
# rather than being baked into ~/Library/LaunchAgents/*.plist.
set -euo pipefail

cd "$(dirname "$0")"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

exec .venv/bin/python server.py
