#!/bin/bash
# setup_cron.sh
# 크론 등록:
#   - 매일 오전 09:00 → run_reels_planner.sh   (AI/디자인 릴스 아이디어)
#   - 매일 오전 09:00 → run_finance_planner.sh  (재테크 릴스 아이디어)
#
# * reels_translator.py (릴스 번역 모니터)는 별도 컴퓨터에서 실행 중 — 여기선 등록 안 함

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

AI_RUNNER="${SCRIPT_DIR}/run_reels_planner.sh"
FINANCE_RUNNER="${SCRIPT_DIR}/run_finance_planner.sh"

chmod +x "$AI_RUNNER"
chmod +x "$FINANCE_RUNNER"

CURRENT=$(crontab -l 2>/dev/null || true)
NEW="$CURRENT"
CHANGED=0

if echo "$CURRENT" | grep -qF "$AI_RUNNER"; then
    echo "✅ AI 릴스 플래너 크론 이미 등록됨"
else
    NEW="${NEW}
0 9 * * * $AI_RUNNER"
    CHANGED=1
    echo "➕ AI 릴스 플래너 등록: 0 9 * * * $AI_RUNNER"
fi

if echo "$CURRENT" | grep -qF "$FINANCE_RUNNER"; then
    echo "✅ 재테크 릴스 플래너 크론 이미 등록됨"
else
    NEW="${NEW}
0 9 * * * $FINANCE_RUNNER"
    CHANGED=1
    echo "➕ 재테크 릴스 플래너 등록: 0 9 * * * $FINANCE_RUNNER"
fi

if [ "$CHANGED" -eq 1 ]; then
    echo "$NEW" | crontab -
    echo ""
    echo "현재 등록된 크론:"
    crontab -l
fi
