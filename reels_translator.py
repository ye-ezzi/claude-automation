"""
릴스 캡션 + 이미지 텍스트 리포터 → Gmail 자동 발송
=====================================================
필요 패키지:
  pip install deep-translator browser-cookie3 requests Pillow pytesseract

필요 프로그램 (OCR용):
  brew install tesseract

동작 방식:
  Chrome에 Instagram 로그인된 상태면 별도 설정 없이 자동 작동
  계정당 최신 릴스 3개의 캡션과 썸네일 텍스트를 한국어로 번역

사용법:
  python reels_translator.py
"""

import os
import sys
import time
import smtplib
import requests
import browser_cookie3
from deep_translator import GoogleTranslator
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

# ══════════════════════════════════════════
#  ✏️  여기를 수정하세요
# ══════════════════════════════════════════

GMAIL_ADDRESS  = "lyj990701@gmail.com"
GMAIL_PASSWORD = "ugfj tqjf xecw wvkv"
TO_ADDRESS     = "lyj990701@gmail.com"
REELS_PER_ACCOUNT = 3  # 계정당 최신 릴스 수

ACCOUNTS = [
    # 기존
    "https://www.instagram.com/thesocialcreativesclub/reels/",
    "https://www.instagram.com/inspiredmediaco/reels/",
    "https://www.instagram.com/creatorcollege_/reels/",
    "https://www.instagram.com/jun_yuh/reels/",
    "https://www.instagram.com/personalbrandlaunch/reels/",
    # 신규
    "https://www.instagram.com/stevenwommack/reels/",
    "https://www.instagram.com/createcontent.club/reels/",
    "https://www.instagram.com/socialcontentking/reels/",
    "https://www.instagram.com/mitchell_tms/reels/",
    "https://www.instagram.com/thebranding.ai/reels/",
    "https://www.instagram.com/bradfordmarais/reels/",
]

# ══════════════════════════════════════════


# ─── Instagram API (Chrome 쿠키) ─────────────────

_ig_session = None

def get_ig_session() -> requests.Session:
    global _ig_session
    if _ig_session is not None:
        return _ig_session
    cookies = browser_cookie3.chrome(domain_name='.instagram.com')
    s = requests.Session()
    s.cookies.update(cookies)
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "x-ig-app-id": "936619743392459",
        "Accept": "*/*",
    })
    _ig_session = s
    return s


def _url_to_username(account_url: str) -> str:
    parts = account_url.rstrip("/").split("/")
    for i, p in enumerate(parts):
        if p in ("reels", "posts") and i > 0:
            return parts[i - 1]
    return parts[-1]


def _get_user_id(username: str):
    s = get_ig_session()
    try:
        resp = s.get(
            f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}",
            timeout=15
        )
        if resp.status_code == 200:
            return resp.json()["data"]["user"]["id"]
        print(f"  ⚠️  user_id 응답 {resp.status_code}")
    except Exception as e:
        print(f"  ❌  user_id 조회 실패: {e}")
    return None


# ─── 메타데이터 수집 ──────────────────────────────

def get_reels_metadata(account_url: str, max_items: int = REELS_PER_ACCOUNT) -> list:
    username = _url_to_username(account_url)
    s = get_ig_session()

    user_id = _get_user_id(username)
    if not user_id:
        print(f"  ❌  user_id 없음 (@{username})")
        return []

    reels = []
    cursor = None

    while len(reels) < max_items:
        params = {"count": 12, "user_id": user_id}
        if cursor:
            params["max_id"] = cursor
        try:
            resp = s.get(
                f"https://www.instagram.com/api/v1/feed/user/{user_id}/",
                params=params, timeout=15
            )
            if resp.status_code != 200:
                print(f"  ⚠️  피드 응답 {resp.status_code}")
                break
            data = resp.json()
        except Exception as e:
            print(f"  ❌  피드 요청 오류: {e}")
            break

        for item in data.get("items", []):
            media_type = item.get("media_type")
            if media_type == 8:
                if not any(m.get("media_type") == 2 for m in item.get("carousel_media", [])):
                    continue
            elif media_type != 2:
                continue

            taken_at = item.get("taken_at", 0)
            upload_date = datetime.fromtimestamp(taken_at).strftime("%Y%m%d") if taken_at else None
            shortcode = item.get("code", item.get("id", ""))
            candidates = item.get("image_versions2", {}).get("candidates", [])
            thumbnail = candidates[0].get("url", "") if candidates else ""
            full_caption = (item.get("caption") or {}).get("text", "")

            reels.append({
                "url":         f"https://www.instagram.com/reel/{shortcode}/",
                "caption":     full_caption,
                "upload_date": upload_date,
                "thumbnail":   thumbnail,
            })
            if len(reels) >= max_items:
                break

        if not data.get("more_available") or not data.get("next_max_id"):
            break
        cursor = data["next_max_id"]
        time.sleep(1.5)

    return reels


# ─── 번역 ─────────────────────────────────────────

def translate_to_korean(text: str) -> str:
    if not text or not text.strip():
        return ""
    try:
        chunks = [text[i:i+4500] for i in range(0, len(text), 4500)]
        return " ".join(
            GoogleTranslator(source="auto", target="ko").translate(chunk)
            for chunk in chunks
        )
    except Exception as e:
        return f"(번역 실패: {e})"


# ─── OCR ──────────────────────────────────────────

def extract_thumbnail_text(thumbnail_url: str) -> str:
    """썸네일 이미지에서 텍스트 추출 (tesseract 필요: brew install tesseract)"""
    if not thumbnail_url:
        return ""
    try:
        import pytesseract
        from PIL import Image, ImageFilter
        import io

        s = get_ig_session()
        resp = s.get(thumbnail_url, timeout=10)
        if resp.status_code != 200:
            return ""

        img = Image.open(io.BytesIO(resp.content))
        # 대비 강화로 OCR 정확도 향상
        img = img.convert("L").filter(ImageFilter.SHARPEN)
        text = pytesseract.image_to_string(img, lang="eng+kor").strip()
        # 의미없는 짧은 결과 제거
        cleaned = " ".join(line.strip() for line in text.splitlines() if len(line.strip()) > 2)
        return cleaned[:400] if cleaned else ""
    except ImportError:
        return ""
    except Exception:
        return ""


# ─── 이메일 빌더 ─────────────────────────────────

def build_html(account_results: list) -> str:
    sections = ""
    for account_url, reels in account_results:
        username = _url_to_username(account_url)
        cards = ""
        for r in reels:
            upload_str = ""
            if r.get("upload_date"):
                try:
                    d = datetime.strptime(r["upload_date"], "%Y%m%d")
                    upload_str = d.strftime("%Y.%m.%d")
                except Exception:
                    pass

            thumbnail_block = (
                f'<img src="{r["thumbnail"]}" '
                f'style="width:100%;max-height:220px;object-fit:cover;" />'
            ) if r.get("thumbnail") else ""

            caption_orig = r.get("caption", "") or ""
            caption_kr   = r.get("caption_kr", "") or ""
            img_text_orig = r.get("img_text", "") or ""
            img_text_kr   = r.get("img_text_kr", "") or ""

            caption_block = f"""
                <p style="margin:10px 0 4px;color:#888;font-size:11px;">📝 캡션 원문</p>
                <p style="margin:0 0 8px;font-size:13px;color:#333;line-height:1.7;white-space:pre-wrap;">{caption_orig[:600]}</p>
                <p style="margin:0 0 4px;color:#888;font-size:11px;">🇰🇷 캡션 번역</p>
                <p style="margin:0 0 14px;font-size:13px;color:#1a1a1a;line-height:1.7;background:#F7F9FC;padding:10px;border-radius:6px;">{caption_kr}</p>
            """ if caption_orig else ""

            img_text_block = f"""
                <p style="margin:0 0 4px;color:#888;font-size:11px;">🖼️ 이미지 텍스트 원문</p>
                <p style="margin:0 0 8px;font-size:13px;color:#555;line-height:1.6;">{img_text_orig}</p>
                <p style="margin:0 0 4px;color:#888;font-size:11px;">🇰🇷 이미지 텍스트 번역</p>
                <p style="margin:0 0 14px;font-size:13px;color:#1a1a1a;line-height:1.7;background:#FFF8F0;padding:10px;border-radius:6px;">{img_text_kr}</p>
            """ if img_text_orig else ""

            cards += f"""
            <div style="margin-bottom:24px;border:1px solid #e0e0e0;border-radius:8px;overflow:hidden;">
              {thumbnail_block}
              <div style="padding:14px;">
                <a href="{r['url']}" style="color:#4A90D9;font-size:12px;word-break:break-all;">{r['url']}</a>
                {"<p style='color:#888;font-size:11px;margin:4px 0;'>📅 " + upload_str + "</p>" if upload_str else ""}
                {caption_block}
                {img_text_block}
              </div>
            </div>"""

        sections += f"""
        <div style="margin-bottom:44px;">
          <h3 style="color:#2D2D2D;border-left:4px solid #4A90D9;padding-left:10px;margin-bottom:16px;">
            @{username}
          </h3>
          {cards if cards else '<p style="color:#aaa;font-size:13px;">수집된 릴스 없음</p>'}
        </div>"""

    return f"""
    <html><body style="font-family:Apple SD Gothic Neo,Arial,sans-serif;max-width:720px;margin:auto;padding:24px;">
      <h2 style="color:#2D2D2D;border-bottom:2px solid #4A90D9;padding-bottom:8px;">
        📋 릴스 캡션 리포트 — 계정당 최신 {REELS_PER_ACCOUNT}개
      </h2>
      <p style="color:#888;font-size:12px;">수집 일시: {datetime.now().strftime('%Y년 %m월 %d일 %H:%M')}</p>
      {sections}
    </body></html>"""


# ─── Gmail 발송 ──────────────────────────────────

def send_gmail(subject: str, html_body: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_ADDRESS
    msg["To"]      = TO_ADDRESS
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, TO_ADDRESS, msg.as_string())


# ─── 메인 로직 ───────────────────────────────────

def run_report():
    print(f"\n📋  릴스 캡션 리포트 수집 시작 ({len(ACCOUNTS)}개 계정)...")
    account_results = []

    for account_url in ACCOUNTS:
        username = _url_to_username(account_url)
        print(f"\n[계정] @{username}")

        reels = get_reels_metadata(account_url, max_items=REELS_PER_ACCOUNT)
        print(f"  → 수집된 릴스: {len(reels)}개")

        processed = []
        for i, reel in enumerate(reels):
            print(f"  [{i+1}/{len(reels)}] 처리 중...")

            # 캡션 번역
            caption_kr = ""
            if reel.get("caption"):
                print(f"    캡션 번역 중...")
                caption_kr = translate_to_korean(reel["caption"])

            # 썸네일 OCR + 번역
            img_text = ""
            img_text_kr = ""
            if reel.get("thumbnail"):
                print(f"    이미지 텍스트 추출 중...")
                img_text = extract_thumbnail_text(reel["thumbnail"])
                if img_text:
                    print(f"    이미지 텍스트 번역 중...")
                    img_text_kr = translate_to_korean(img_text)

            processed.append({
                **reel,
                "caption_kr":  caption_kr,
                "img_text":    img_text,
                "img_text_kr": img_text_kr,
            })
            time.sleep(1)

        account_results.append((account_url, processed))
        time.sleep(3)

    print("\n📬  이메일 발송 중...")
    subject = f"📋 릴스 캡션 리포트 — {datetime.now().strftime('%Y.%m.%d')} ({len(ACCOUNTS)}개 계정)"
    html = build_html(account_results)
    send_gmail(subject, html)
    print("✅  발송 완료!")


def main():
    run_report()


if __name__ == "__main__":
    main()
