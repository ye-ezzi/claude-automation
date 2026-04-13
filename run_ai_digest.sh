#!/bin/bash
# run_ai_digest.sh
# AI 콘텐츠 다이제스트 수집 및 이메일 발송

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="${SCRIPT_DIR}/venv/bin/python3"
LOG_DIR="$HOME/logs"
LOG_FILE="${LOG_DIR}/ai_digest_$(date '+%Y-%m-%d').log"

mkdir -p "$LOG_DIR"

# .env 파일에서 환경변수 로드
if [ -f "${SCRIPT_DIR}/.env" ]; then
    export $(grep -v '^#' "${SCRIPT_DIR}/.env" | xargs)
fi

# 가상환경이 없으면 자동 설치
if [ ! -f "$VENV_PYTHON" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 가상환경이 없습니다. 자동 설치 중..." >> "$LOG_FILE"
    bash "${SCRIPT_DIR}/setup_venv.sh" >> "$LOG_FILE" 2>&1
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting ai_digest.py --ig-only" >> "$LOG_FILE"

OUTPUT=$(cd "$SCRIPT_DIR" && "$VENV_PYTHON" ai_digest.py --ig-only 2>&1)
EXIT_CODE=$?

echo "$OUTPUT" >> "$LOG_FILE"

if [ $EXIT_CODE -eq 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 완료 (exit code: 0)" >> "$LOG_FILE"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 오류 발생 (exit code: $EXIT_CODE)" >> "$LOG_FILE"
fi
