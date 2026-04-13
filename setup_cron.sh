#!/bin/bash
# setup_cron.sh
# 크론 등록 (개인컴/회사컴 공통):
#   - 매일 오전 08:00 → run_ai_digest.sh        (AI 채널 콘텐츠 수집)
#   - 매일 오전 09:00 → run_reels_planner.sh    (AI/디자인 릴스 아이디어)
#   - 매일 오전 09:00 → run_finance_planner.sh  (재테크 릴스 아이디어)
#   - 매일 오후 21:00 → run_reels_monitor.sh    (인스타 릴스 번역)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

DIGEST_RUNNER="${SCRIPT_DIR}/run_ai_digest.sh"
AI_RUNNER="${SCRIPT_DIR}/run_reels_planner.sh"
FINANCE_RUNNER="${SCRIPT_DIR}/run_finance_planner.sh"
MONITOR_RUNNER="${SCRIPT_DIR}/run_reels_monitor.sh"

chmod +x "$DIGEST_RUNNER" "$AI_RUNNER" "$FINANCE_RUNNER" "$MONITOR_RUNNER"

CURRENT=$(crontab -l 2>/dev/null || true)
NEW="$CURRENT"
CHANGED=0

register_cron() {
    local label="$1"
    local schedule="$2"
    local runner="$3"
    if echo "$CURRENT" | grep -qF "$runner"; then
        echo "✅ ${label} 크론 이미 등록됨"
    else
        NEW="${NEW}
${schedule} $runner"
        CHANGED=1
        echo "➕ ${label} 등록: ${schedule} $runner"
    fi
}

register_cron "AI 다이제스트"      "0 8  * * *" "$DIGEST_RUNNER"
register_cron "AI 릴스 플래너"     "0 9  * * *" "$AI_RUNNER"
register_cron "재테크 릴스 플래너" "0 9  * * *" "$FINANCE_RUNNER"
register_cron "릴스 번역 모니터"   "0 21 * * *" "$MONITOR_RUNNER"

if [ "$CHANGED" -eq 1 ]; then
    echo "$NEW" | crontab -
    echo ""
    echo "현재 등록된 크론:"
    crontab -l
fi
