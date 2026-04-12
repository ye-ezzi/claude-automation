"""
카드뉴스 자동 생성 메인 스크립트

사용법:
  python3 main.py              # 전체 채널 처리
  python3 main.py 재테크        # 특정 채널만 처리
  python3 main.py 재테크 마케팅  # 여러 채널 처리
"""

import sys
import time
from pathlib import Path

from sheets_agent import load_config, read_pending_rows, write_generated
from body_agent import generate

BASE = Path(__file__).parent


def process_channel(channel_name: str, channel_cfg: dict):
    tab = channel_cfg["sheet_tab"]
    print(f"\n{'='*50}")
    print(f"  채널: {channel_name} (탭: {tab})")
    print(f"{'='*50}")

    pending = read_pending_rows(tab, channel_cfg)
    print(f"  대기중인 행: {len(pending)}개")

    if not pending:
        print("  → 처리할 행 없음")
        return

    for row_index, row in pending:
        folder = row.get("폴더명", f"row_{row_index}")
        print(f"\n  [{row_index}행] {folder}")

        try:
            updates = generate(row, channel_cfg)
            if updates:
                write_generated(tab, row_index, updates, channel_cfg)
            else:
                print(f"  ⚠️  생성 실패 — 건너뜀")
        except Exception as e:
            print(f"  ❌ 오류: {e}")

        time.sleep(1)  # API 호출 간격


def main():
    config = load_config()
    channels = config.get("channels", {})

    # 실행할 채널 결정
    if len(sys.argv) > 1:
        target_channels = sys.argv[1:]
    else:
        target_channels = list(channels.keys())

    print(f"\n🚀 카드뉴스 자동 생성 시작")
    print(f"   처리 채널: {', '.join(target_channels)}")

    for name in target_channels:
        if name not in channels:
            print(f"  ⚠️  '{name}' 채널이 config.yaml에 없습니다.")
            print(f"      사용 가능: {', '.join(channels.keys())}")
            continue
        process_channel(name, channels[name])

    print(f"\n✅ 완료!")


if __name__ == "__main__":
    main()
