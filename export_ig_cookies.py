"""
Instagram Chrome 쿠키 → ig_cookies.json 저장
=====================================================
cron은 macOS Keychain에 접근 못해서 browser_cookie3가 실패함.
이 스크립트를 터미널에서 1회 실행하면 쿠키를 파일로 저장해두고
reels_translator.py가 cron에서도 파일을 읽어 동작함.

사용법:
  cd ~/claude-automation
  python3 export_ig_cookies.py

쿠키 만료 시 (보통 몇 주~몇 달):
  Chrome에서 Instagram 재로그인 후 이 스크립트 재실행
"""

import browser_cookie3
import json
import os

def main():
    print("Chrome Instagram 쿠키 읽는 중...")
    try:
        cookies = browser_cookie3.chrome(domain_name='.instagram.com')
        cookie_list = [
            {"name": c.name, "value": c.value, "domain": c.domain}
            for c in cookies
        ]
    except Exception as e:
        print(f"❌ 쿠키 읽기 실패: {e}")
        print("Chrome이 설치되어 있고 Instagram에 로그인되어 있는지 확인하세요.")
        return

    if not cookie_list:
        print("❌ Instagram 쿠키가 없습니다. Chrome에서 instagram.com에 로그인하세요.")
        return

    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ig_cookies.json")
    with open(output_path, "w") as f:
        json.dump(cookie_list, f)

    print(f"✅ 쿠키 {len(cookie_list)}개 저장 완료: {output_path}")
    print("이제 cron에서 reels_translator.py가 정상 실행됩니다.")

if __name__ == "__main__":
    main()
