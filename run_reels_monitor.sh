#!/bin/bash
# run_reels_monitor.sh
# Runs reels_translator.py --monitor and emails results to lyj990701@gmail.com

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="${SCRIPT_DIR}/venv/bin/python3"
TO_EMAIL="lyj990701@gmail.com"
LOG_DIR="$HOME/logs"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
LOG_FILE="${LOG_DIR}/reels_monitor_$(date '+%Y-%m-%d').log"

mkdir -p "$LOG_DIR"

# 가상환경이 없으면 자동 설치
if [ ! -f "$VENV_PYTHON" ]; then
    echo "[$TIMESTAMP] 가상환경이 없습니다. 자동 설치 중..." >> "$LOG_FILE"
    bash "${SCRIPT_DIR}/setup_venv.sh" >> "$LOG_FILE" 2>&1
fi

echo "[$TIMESTAMP] Starting reels_translator.py --monitor" >> "$LOG_FILE"

OUTPUT=$(cd "$SCRIPT_DIR" && "$VENV_PYTHON" reels_translator.py --monitor 2>&1)
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
