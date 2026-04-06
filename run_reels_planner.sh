#!/bin/bash
# run_reels_planner.sh
# 매일 오전 9시 reels_planner.py 실행 → 결과 이메일 발송

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
LOG_DIR="${HOME}/logs"
LOG_FILE="${LOG_DIR}/reels_planner_$(date '+%Y-%m-%d').log"

mkdir -p "$LOG_DIR"

echo "[$TIMESTAMP] 릴스 플래너 시작" >> "$LOG_FILE"

# ANTHROPIC_API_KEY가 환경변수에 없으면 .env 파일에서 로드
if [ -z "$ANTHROPIC_API_KEY" ] && [ -f "${SCRIPT_DIR}/.env" ]; then
    export $(grep -v '^#' "${SCRIPT_DIR}/.env" | xargs)
fi

OUTPUT=$(cd "$SCRIPT_DIR" && python3 AI_reels_planner.py 2>&1)
EXIT_CODE=$?

echo "$OUTPUT" >> "$LOG_FILE"
echo "[$TIMESTAMP] 완료 (exit code: $EXIT_CODE)" >> "$LOG_FILE"

# 실행 결과 요약 이메일 (실패 시만)
if [ $EXIT_CODE -ne 0 ]; then
    SUBJECT="[오류] 릴스 플래너 실패 — $(date '+%Y-%m-%d')"
    BODY="❌ reels_planner.py 실행 중 오류가 발생했습니다.

실행 시각: $TIMESTAMP
로그 파일: $LOG_FILE

--- 오류 내용 ---
$OUTPUT"
    echo "$BODY" | mail -s "$SUBJECT" "lyj990701@gmail.com" 2>/dev/null || true
fi
