#!/bin/bash
# Remove the scheduled jobs.
DEST="$HOME/Library/LaunchAgents"
for job in com.istock.prices com.istock.scores; do
    launchctl unload "$DEST/$job.plist" 2>/dev/null || true
    rm -f "$DEST/$job.plist"
    echo "removed $job"
done
