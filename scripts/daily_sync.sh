#!/bin/bash
# MyTrainingOS Daily Sync Script
# Syncs Garmin and Oura data

LOG_DIR="$HOME/.gemini/antigravity/scratch/mytrainingos/logs"
LOG_FILE="$LOG_DIR/sync_$(date +%Y%m%d).log"
APP_DIR="$HOME/.gemini/antigravity/scratch/mytrainingos"

# Create log directory
mkdir -p "$LOG_DIR"

echo "=== Sync started at $(date) ===" >> "$LOG_FILE"

# Sync Oura
echo "Syncing Oura..." >> "$LOG_FILE"
cd "$APP_DIR" && /usr/bin/python3 oura_sync.py >> "$LOG_FILE" 2>&1
OURA_RESULT=$?

# Sync Garmin (if script exists)
if [ -f "$APP_DIR/sync_garmin.py" ]; then
    echo "Syncing Garmin..." >> "$LOG_FILE"
    cd "$APP_DIR" && /usr/bin/python3 sync_garmin.py >> "$LOG_FILE" 2>&1
    GARMIN_RESULT=$?
else
    GARMIN_RESULT=0
    echo "Garmin sync script not found, skipping" >> "$LOG_FILE"
fi

echo "=== Sync completed at $(date) ===" >> "$LOG_FILE"
echo "Oura: $OURA_RESULT, Garmin: $GARMIN_RESULT" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

# Keep only last 7 days of logs
find "$LOG_DIR" -name "sync_*.log" -mtime +7 -delete
