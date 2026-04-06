#!/bin/bash
# setup_cron.sh
# 크론 등록:
#   - 매일 오전 09:00 → run_reels_planner.sh  (릴스 아이디어 생성 + 발송)
#   - 매일 오후 21:00 → run_reels_monitor.sh   (릴스 번역 모니터링)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PLANNER_RUNNER="${SCRIPT_DIR}/run_reels_planner.sh"
MONITOR_RUNNER="${SCRIPT_DIR}/run_reels_monitor.sh"

chmod +x "$PLANNER_RUNNER"
chmod +x "$MONITOR_RUNNER"

PLANNER_CRON="0 9 * * * $PLANNER_RUNNER"
MONITOR_CRON="0 21 * * * $MONITOR_RUNNER"

CURRENT_CRONTAB=$(crontab -l 2>/dev/null || true)
NEW_CRONTAB="$CURRENT_CRONTAB"
CHANGED=0

if echo "$CURRENT_CRONTAB" | grep -qF "$PLANNER_RUNNER"; then
    echo "✅ 릴스 플래너 크론 이미 등록됨:"
    echo "   $(echo "$CURRENT_CRONTAB" | grep "$PLANNER_RUNNER")"
else
    NEW_CRONTAB="${NEW_CRONTAB}
${PLANNER_CRON}"
    CHANGED=1
    echo "➕ 릴스 플래너 크론 등록: $PLANNER_CRON"
fi

if echo "$CURRENT_CRONTAB" | grep -qF "$MONITOR_RUNNER"; then
    echo "✅ 릴스 모니터 크론 이미 등록됨:"
    echo "   $(echo "$CURRENT_CRONTAB" | grep "$MONITOR_RUNNER")"
else
    NEW_CRONTAB="${NEW_CRONTAB}
${MONITOR_CRON}"
    CHANGED=1
    echo "➕ 릴스 모니터 크론 등록: $MONITOR_CRON"
fi

if [ "$CHANGED" -eq 1 ]; then
    echo "$NEW_CRONTAB" | crontab -
    echo ""
    echo "현재 등록된 크론:"
    crontab -l
fi
