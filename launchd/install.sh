#!/bin/bash
# Install the CatchingApril LaunchAgents (poller + server).
#
# Templates in this directory use __USER_HOME__ as a placeholder; this
# script substitutes $HOME, copies the result to ~/Library/LaunchAgents/,
# and loads each agent so it starts immediately and re-launches at login.
#
# Safe to re-run: existing agents are unloaded and replaced.
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/Library/LaunchAgents"
LOGS="$HOME/Library/Logs"

mkdir -p "$DEST" "$LOGS"

for label in com.catchingapril.poller com.catchingapril.server; do
  src_plist="$SRC/$label.plist"
  dst_plist="$DEST/$label.plist"

  if [ ! -f "$src_plist" ]; then
    echo "Missing template: $src_plist" >&2
    exit 1
  fi

  # Unload any previous version before overwriting (ignore errors if not loaded).
  launchctl unload "$dst_plist" 2>/dev/null || true

  sed "s|__USER_HOME__|$HOME|g" "$src_plist" > "$dst_plist"
  launchctl load "$dst_plist"

  echo "Installed and loaded: $dst_plist"
done

echo ""
echo "Verify:"
echo "  launchctl list | grep catchingapril"
echo "  tail -f $LOGS/catchingapril-poller.log"
echo "  tail -f $LOGS/catchingapril-server.log"
echo "  curl -s http://localhost:5000/api/days"
