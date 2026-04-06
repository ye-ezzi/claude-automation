#!/bin/bash
# setup_cron.sh
# Installs a cron job to run reels_monitor every day at 9 PM (21:00)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="${SCRIPT_DIR}/run_reels_monitor.sh"

chmod +x "$RUNNER"

CRON_JOB="0 21 * * * $RUNNER"

# Check if already installed
if crontab -l 2>/dev/null | grep -qF "$RUNNER"; then
    echo "Cron job already exists:"
    crontab -l | grep "$RUNNER"
    exit 0
fi

# Append cron job
( crontab -l 2>/dev/null; echo "$CRON_JOB" ) | crontab -

echo "Cron job installed:"
crontab -l | grep "$RUNNER"
