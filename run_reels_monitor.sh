#!/bin/bash
# run_reels_monitor.sh
# Runs reels_translator.py --monitor and emails results to lyj990701@gmail.com

TO_EMAIL="lyj990701@gmail.com"
LOG_DIR="/Users/comcom/logs"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
LOG_FILE="${LOG_DIR}/reels_monitor_$(date '+%Y-%m-%d').log"

mkdir -p "$LOG_DIR"

echo "[$TIMESTAMP] Starting reels_translator.py --monitor" >> "$LOG_FILE"

OUTPUT=$(cd /Users/comcom && python3 reels_translator.py --monitor 2>&1)
EXIT_CODE=$?

echo "$OUTPUT" >> "$LOG_FILE"

if [ $EXIT_CODE -eq 0 ]; then
    SUBJECT="[완료] Reels Translator Monitor - $(date '+%Y-%m-%d')"
    BODY="✅ 정상 완료되었습니다.

실행 시각: $TIMESTAMP

--- 실행 결과 ---
$OUTPUT"
else
    SUBJECT="[오류] Reels Translator Monitor - $(date '+%Y-%m-%d')"
    BODY="❌ 오류가 발생했습니다. (exit code: $EXIT_CODE)

실행 시각: $TIMESTAMP

--- 오류 내용 ---
$OUTPUT"
fi

echo "$BODY" | mail -s "$SUBJECT" "$TO_EMAIL"

echo "[$TIMESTAMP] Email sent to $TO_EMAIL (exit code: $EXIT_CODE)" >> "$LOG_FILE"
