#!/bin/bash
# Uninstall the CatchingApril LaunchAgents.
# Stops both services and removes the plists from ~/Library/LaunchAgents/.
set -euo pipefail

DEST="$HOME/Library/LaunchAgents"

for label in com.catchingapril.poller com.catchingapril.server; do
  plist="$DEST/$label.plist"
  if [ -f "$plist" ]; then
    launchctl unload "$plist" 2>/dev/null || true
    rm "$plist"
    echo "Removed: $plist"
  else
    echo "(not installed: $plist)"
  fi
done
