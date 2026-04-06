#!/bin/bash
# run_reels_monitor.sh
# Runs reels_translator.py --monitor and logs output/errors

LOG_DIR="/Users/comcom/logs"
TIMESTAMP=$(date '+%Y-%m-%d_%H-%M-%S')
LOG_FILE="${LOG_DIR}/reels_monitor_${TIMESTAMP}.log"
ERROR_FILE="${LOG_DIR}/reels_monitor_${TIMESTAMP}.error.log"

mkdir -p "$LOG_DIR"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting reels_translator.py --monitor" | tee -a "$LOG_FILE"

cd /Users/comcom && python3 reels_translator.py --monitor \
    1>>"$LOG_FILE" \
    2>>"$ERROR_FILE"

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Completed successfully (exit code: 0)" | tee -a "$LOG_FILE"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: Script exited with code $EXIT_CODE" | tee -a "$LOG_FILE"
    echo "" >> "$LOG_FILE"
    echo "=== Error Output ===" >> "$LOG_FILE"
    cat "$ERROR_FILE" >> "$LOG_FILE"

    # Optional: send error notification via system mail if available
    if command -v mail &>/dev/null && [ -n "$NOTIFY_EMAIL" ]; then
        mail -s "[ERROR] reels_translator.py --monitor failed (exit $EXIT_CODE)" "$NOTIFY_EMAIL" < "$ERROR_FILE"
    fi

    exit $EXIT_CODE
fi
