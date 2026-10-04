#!/bin/bash
# Install the daily-price + weekly-score scheduled jobs (macOS launchd).
# Run once:  bash schedule/install.sh
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="$HOME/Library/LaunchAgents"
mkdir -p "$DEST"
for job in com.istock.prices com.istock.scores; do
    cp "$DIR/$job.plist" "$DEST/$job.plist"
    launchctl unload "$DEST/$job.plist" 2>/dev/null || true
    launchctl load "$DEST/$job.plist"
    echo "loaded $job"
done
echo "Done. Jobs: prices daily 11:00, scores weekly Sat 11:30 (IST / local time)."
echo "Check status:  launchctl list | grep istock"
echo "Uninstall:     bash schedule/uninstall.sh"
