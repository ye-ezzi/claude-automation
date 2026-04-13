#!/bin/bash
# setup_cron.sh
# 크론 등록: 매일 오후 21:00 → run_reels_monitor.sh (인스타 릴스 번역)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="${SCRIPT_DIR}/run_reels_monitor.sh"

chmod +x "$RUNNER"

CRON_JOB="0 21 * * * $RUNNER"

if crontab -l 2>/dev/null | grep -qF "$RUNNER"; then
    echo "✅ 릴스 번역 모니터 크론 이미 등록됨:"
    crontab -l | grep "$RUNNER"
    exit 0
fi

( crontab -l 2>/dev/null; echo "$CRON_JOB" ) | crontab -

echo "✅ 크론 등록 완료:"
crontab -l | grep "$RUNNER"
