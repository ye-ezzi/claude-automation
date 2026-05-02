"""
릴스 음성 번역기 → Gmail 자동 발송
=====================================================
필요 패키지 설치:
  pip install yt-dlp openai-whisper deep-translator browser-cookie3 requests

필요 프로그램:
  ffmpeg 설치 필요

동작 방식:
  Chrome에 Instagram 로그인된 상태면 별도 설정 없이 자동 작동

사용법:
  python reels_translator.py            # 전체 리포트 실행
  python reels_translator.py --report   # 전체 리포트만
  python reels_translator.py --monitor  # 오늘 신규 게시물 알림만
"""

import os
import sys
import time
import smtplib
import whisper
import yt_dlp
import requests
import browser_cookie3
from deep_translator import GoogleTranslator
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta

# ══════════════════════════════════════════
#  ✏️  여기를 수정하세요
# ══════════════════════════════════════════

GMAIL_ADDRESS  = "lyj990701@gmail.com"
GMAIL_PASSWORD = "ugfj tqjf xecw wvkv"
TO_ADDRESS     = "lyj990701@gmail.com"
WHISPER_MODEL  = "medium"
TEMP_DIR       = "./temp_audio"
MAX_AGE_MONTHS    = 6    # 업로드 후 6개월 이내
TOP_N_PER_ACCOUNT = 3    # 계정당 조회수 상위 N개
FETCH_LIMIT       = 50   # 계정당 최대 가져올 릴스 수

# 전체 리포트 대상 계정
ACCOUNT_URLS = [
    "https://www.instagram.com/thesocialcreativesclub/reels/",
    "https://www.instagram.com/inspiredmediaco/reels/",
    "https://www.instagram.com/creatorcollege_/reels/",
    "https://www.instagram.com/jun_yuh/reels/",
    "https://www.instagram.com/personalbrandlaunch/reels/",
]

# 신규 게시물 즉시 알림 계정
MONITOR_ACCOUNTS = [
    "https://www.instagram.com/thesocialcreativesclub/reels/",
    "https://www.instagram.com/inspiredmediaco/reels/",
    "https://www.instagram.com/creatorcollege_/reels/",
    "https://www.instagram.com/jun_yuh/reels/",
    "https://www.instagram.com/personalbrandlaunch/reels/",
]

# 캡션 리포트 전용 벤치마크 계정 (Whisper 없이 캡션+링크만)
BENCHMARK_ACCOUNTS = [
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
    """Chrome 쿠키로 인증된 Instagram 세션 반환 (싱글턴)"""
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
    """URL에서 Instagram 유저명 추출"""
    parts = account_url.rstrip("/").split("/")
    for i, p in enumerate(parts):
        if p in ("reels", "posts") and i > 0:
            return parts[i - 1]
    return parts[-1]


def _get_user_id(username: str):
    """유저명 → Instagram user_id"""
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

def get_reels_metadata(account_url: str, max_items: int = FETCH_LIMIT) -> list:
    """Chrome 쿠키 + Instagram API로 릴스 메타데이터 수집"""
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
            # 2=단일 동영상, 8=캐러셀(동영상 포함 여부 체크)
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
                "id":          shortcode,
                "url":         f"https://www.instagram.com/reel/{shortcode}/",
                "title":       full_caption[:80],
                "caption":     full_caption,
                "view_count":  item.get("view_count") or item.get("play_count") or 0,
                "upload_date": upload_date,
                "thumbnail":   thumbnail,
                "account_url": account_url,
            })
            if len(reels) >= max_items:
                break

        if not data.get("more_available") or not data.get("next_max_id"):
            break
        cursor = data["next_max_id"]
        time.sleep(1.5)

    return reels


def filter_recent(reels: list, months: int = MAX_AGE_MONTHS) -> list:
    """업로드 날짜 기준 N개월 이내 필터링"""
    cutoff = datetime.now() - timedelta(days=months * 30)
    result = []
    for r in reels:
        if r["upload_date"]:
            try:
                upload_dt = datetime.strptime(r["upload_date"], "%Y%m%d")
                if upload_dt >= cutoff:
                    result.append(r)
            except ValueError:
                result.append(r)
        else:
            result.append(r)
    return result


def sort_by_views(reels: list) -> list:
    """조회수 내림차순 정렬"""
    return sorted(reels, key=lambda r: r["view_count"], reverse=True)


def try_ocr_thumbnail(thumbnail_url: str) -> str:
    """썸네일 이미지에서 텍스트 OCR (pytesseract 선택적 의존)"""
    try:
        import pytesseract
        from PIL import Image
        import io
        s = get_ig_session()
        resp = s.get(thumbnail_url, timeout=10)
        if resp.status_code != 200:
            return ""
        img = Image.open(io.BytesIO(resp.content))
        text = pytesseract.image_to_string(img, lang="eng").strip()
        return " ".join(text.split())[:300] if text else ""
    except ImportError:
        return "[OCR 불가: pytesseract/Pillow 미설치]"
    except Exception:
        return ""


# ─── 음성 처리 ───────────────────────────────────

def _find_ffmpeg() -> str:
    """ffmpeg 경로 자동 탐색 (brew 설치 경로 포함)"""
    import shutil
    for path in [
        shutil.which("ffmpeg"),
        "/opt/homebrew/bin/ffmpeg",   # Apple Silicon Mac
        "/usr/local/bin/ffmpeg",       # Intel Mac
    ]:
        if path and os.path.exists(path):
            return os.path.dirname(path)
    return ""


def download_audio(url: str, output_path: str) -> str:
    """릴스에서 음성만 추출"""
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_path,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
        "quiet": True,
        "noprogress": True,
        "no_warnings": True,
        "cookiesfrombrowser": ("chrome",),
        "ffmpeg_location": _find_ffmpeg(),
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    return output_path + ".mp3"


def transcribe_audio(audio_path: str, model) -> str:
    """Whisper로 음성 → 텍스트"""
    result = model.transcribe(audio_path)
    return result["text"].strip()


def translate_to_korean(text: str) -> str:
    """영어 → 한국어 번역"""
    if not text:
        return ""
    try:
        return GoogleTranslator(source="auto", target="ko").translate(text[:4999])
    except Exception as e:
        return f"[번역 오류: {e}]"


def process_reel(reel: dict, model, index: int) -> dict:
    """릴스 1개 다운로드 → 음성인식 → 번역"""
    audio_path = os.path.join(TEMP_DIR, f"reel_{index}")
    url = reel["url"]

    try:
        print(f"  📥  음성 추출 중... ({url})")
        mp3_path = download_audio(url, audio_path)

        print("  🎙️  음성 인식 중...")
        original_text = transcribe_audio(mp3_path, model)
        print(f"  원문: {original_text[:80]}...")

        print("  🇰🇷  번역 중...")
        translated_text = translate_to_korean(original_text)
        print(f"  번역: {translated_text[:80]}...")

        if os.path.exists(mp3_path):
            os.remove(mp3_path)

        return {**reel, "original": original_text, "translated": translated_text, "error": None}

    except Exception as e:
        print(f"  ❌  오류: {e}")
        if os.path.exists(audio_path + ".mp3"):
            os.remove(audio_path + ".mp3")
        return {**reel, "original": "", "translated": "", "error": str(e)}


# ─── 모니터링 ────────────────────────────────────

def find_todays_reels(account_url: str, target_date: str = None) -> list:
    """특정 날짜에 업로드된 릴스 반환 (기본값: 오늘)"""
    date = target_date or datetime.now().strftime("%Y%m%d")
    reels = get_reels_metadata(account_url, max_items=20)
    return [r for r in reels if r.get("upload_date") == date]


# ─── 이메일 빌더 ─────────────────────────────────

def _reel_card_html(r: dict, rank: int = None) -> str:
    upload_str = ""
    if r.get("upload_date"):
        try:
            d = datetime.strptime(r["upload_date"], "%Y%m%d")
            upload_str = d.strftime("%Y.%m.%d")
        except Exception:
            pass

    view_str = f"{r['view_count']:,}" if r.get("view_count") else "조회수 미제공"
    rank_badge = f'<span style="background:#4A90D9;color:#fff;padding:2px 8px;border-radius:12px;font-size:12px;">#{rank}</span> ' if rank else ""
    error_block = f'<p style="color:#c00;font-size:13px;">[오류] {r["error"]}</p>' if r.get("error") else ""
    thumbnail = f'<img src="{r["thumbnail"]}" style="width:100%;max-height:200px;object-fit:cover;" />' if r.get("thumbnail") else ""

    return f"""
    <div style="margin-bottom:28px;border:1px solid #e0e0e0;border-radius:8px;overflow:hidden;">
      {thumbnail}
      <div style="background:#2D2D2D;padding:10px 14px;display:flex;align-items:center;gap:8px;">
        {rank_badge}
        <a href="{r['url']}" style="color:#7EC8F0;font-size:12px;word-break:break-all;">{r['url']}</a>
      </div>
      <div style="padding:14px;">
        <p style="margin:0 0 6px;color:#888;font-size:11px;">
          👁️ {view_str}
          {"&nbsp;·&nbsp;📅 " + upload_str if upload_str else ""}
        </p>
        {error_block}
        <p style="margin:8px 0 4px;color:#888;font-size:11px;">🎙️ 원문</p>
        <p style="margin:0 0 12px;font-size:13px;color:#333;line-height:1.7;">{r.get('original') or '(음성 없음)'}</p>
        <p style="margin:0 0 4px;color:#888;font-size:11px;">🇰🇷 한국어 번역</p>
        <p style="margin:0;font-size:13px;color:#1a1a1a;line-height:1.7;background:#F7F9FC;padding:10px;border-radius:6px;">{r.get('translated') or '(번역 없음)'}</p>
      </div>
    </div>
    """


def build_report_html(account_results: list) -> str:
    """계정별 섹션으로 구성된 전체 리포트 HTML"""
    sections = ""
    for account_url, reels in account_results:
        username = _url_to_username(account_url)
        cards = "".join(_reel_card_html(r, rank=i+1) for i, r in enumerate(reels))
        sections += f"""
        <div style="margin-bottom:40px;">
          <h3 style="color:#2D2D2D;border-left:4px solid #4A90D9;padding-left:10px;margin-bottom:16px;">
            @{username}
          </h3>
          {cards if cards else '<p style="color:#aaa;font-size:13px;">필터 조건에 맞는 릴스가 없습니다.</p>'}
        </div>
        """

    return f"""
    <html><body style="font-family:Apple SD Gothic Neo,Arial,sans-serif;max-width:720px;margin:auto;padding:24px;">
      <h2 style="color:#2D2D2D;border-bottom:2px solid #4A90D9;padding-bottom:8px;">
        📊 릴스 리포트 — 조회수 TOP {TOP_N_PER_ACCOUNT} (6개월 이내)
      </h2>
      <p style="color:#888;font-size:12px;">수집 일시: {datetime.now().strftime('%Y년 %m월 %d일 %H:%M')}</p>
      {sections}
    </body></html>
    """


def build_alert_html(new_reels: list, account_url: str) -> str:
    """신규 게시물 알림 이메일 HTML"""
    username = _url_to_username(account_url)
    cards = "".join(_reel_card_html(r) for r in new_reels)
    return f"""
    <html><body style="font-family:Apple SD Gothic Neo,Arial,sans-serif;max-width:720px;margin:auto;padding:24px;">
      <h2 style="color:#2D2D2D;border-bottom:2px solid #E87040;padding-bottom:8px;">
        🔔 오늘의 릴스 알림 — @{username}
      </h2>
      <p style="color:#888;font-size:12px;">감지 일시: {datetime.now().strftime('%Y년 %m월 %d일 %H:%M')}</p>
      {cards}
    </body></html>
    """


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

def run_report(model):
    """전체 계정 리포트: 6개월 이내 + 조회수 상위 N개"""
    print("\n📊  전체 리포트 수집 시작...")
    account_results = []

    for account_url in ACCOUNT_URLS:
        username = _url_to_username(account_url)
        print(f"\n[계정] @{username}")

        reels = get_reels_metadata(account_url)
        print(f"  → 수집된 릴스: {len(reels)}개")

        reels = filter_recent(reels)
        print(f"  → 6개월 이내 필터: {len(reels)}개")

        reels = sort_by_views(reels)
        top_reels = reels[:TOP_N_PER_ACCOUNT]
        print(f"  → 조회수 상위 {TOP_N_PER_ACCOUNT}개 처리")

        processed = []
        for i, reel in enumerate(top_reels):
            result = process_reel(reel, model, index=i)
            processed.append(result)
            time.sleep(2)

        account_results.append((account_url, processed))
        time.sleep(5)  # 계정 간 딜레이

    if account_results:
        print("\n📬  리포트 이메일 발송 중...")
        subject = f"릴스 리포트 {datetime.now().strftime('%Y.%m.%d')} — 조회수 TOP{TOP_N_PER_ACCOUNT} × {len(ACCOUNT_URLS)}계정"
        html = build_report_html(account_results)
        send_gmail(subject, html)
        print("✅  리포트 발송 완료!")


def run_monitor(model, target_date: str = None):
    """모니터링 계정의 오늘 업로드된 릴스 확인 및 알림 (전체 1통)"""
    label = target_date or datetime.now().strftime("%Y%m%d")
    print(f"\n🔔  릴스 확인 ({label})...")

    account_results = []

    for account_url in MONITOR_ACCOUNTS:
        username = _url_to_username(account_url)
        print(f"[모니터] @{username}")

        todays_reels = find_todays_reels(account_url, target_date)
        print(f"  → 업로드된 릴스: {len(todays_reels)}개")

        if todays_reels:
            processed = []
            for i, reel in enumerate(todays_reels):
                result = process_reel(reel, model, index=i)
                processed.append(result)
                time.sleep(2)
            account_results.append((account_url, processed))
        else:
            print("  → 오늘 업로드된 게시물 없음")

    if account_results:
        total = sum(len(reels) for _, reels in account_results)
        date_str = datetime.strptime(label, "%Y%m%d").strftime("%Y.%m.%d")
        print("\n📬  알림 이메일 발송 중...")
        subject = f"📅 오늘의 릴스 — {len(account_results)}개 계정 · {total}개 ({date_str})"
        html = build_report_html(account_results)
        send_gmail(subject, html)
        print("✅  알림 발송 완료!")
    else:
        print("\n업로드된 게시물 없음 — 이메일 발송 생략")


def build_caption_report_html(account_results: list) -> str:
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
            thumbnail = f'<img src="{r["thumbnail"]}" style="width:100%;max-height:200px;object-fit:cover;" />' if r.get("thumbnail") else ""
            ocr_block = f'<p style="margin:6px 0;color:#777;font-size:11px;">🖼️ 이미지 텍스트: {r["thumbnail_text"]}</p>' if r.get("thumbnail_text") else ""
            caption_text = r.get("caption", "(캡션 없음)") or "(캡션 없음)"
            translated_text = r.get("translated", "(번역 없음)") or "(번역 없음)"
            cards += f"""
            <div style="margin-bottom:20px;border:1px solid #e0e0e0;border-radius:8px;overflow:hidden;">
              {thumbnail}
              <div style="padding:14px;">
                <a href="{r['url']}" style="color:#4A90D9;font-size:12px;word-break:break-all;">{r['url']}</a>
                {"<p style='color:#888;font-size:11px;margin:4px 0;'>📅 " + upload_str + "</p>" if upload_str else ""}
                {ocr_block}
                <p style="margin:10px 0 4px;color:#888;font-size:11px;">📝 원문 캡션</p>
                <p style="margin:0 0 12px;font-size:13px;color:#333;line-height:1.7;white-space:pre-wrap;">{caption_text[:600]}</p>
                <p style="margin:0 0 4px;color:#888;font-size:11px;">🇰🇷 한국어 번역</p>
                <p style="margin:0;font-size:13px;color:#1a1a1a;line-height:1.7;background:#F7F9FC;padding:10px;border-radius:6px;">{translated_text}</p>
              </div>
            </div>"""
        sections += f"""
        <div style="margin-bottom:40px;">
          <h3 style="color:#2D2D2D;border-left:4px solid #E87040;padding-left:10px;margin-bottom:16px;">@{username}</h3>
          {cards}
        </div>"""
    return f"""
    <html><body style="font-family:Apple SD Gothic Neo,Arial,sans-serif;max-width:720px;margin:auto;padding:24px;">
      <h2 style="color:#2D2D2D;border-bottom:2px solid #E87040;padding-bottom:8px;">📋 벤치마크 캡션 리포트</h2>
      <p style="color:#888;font-size:12px;">수집 일시: {datetime.now().strftime('%Y년 %m월 %d일 %H:%M')}</p>
      {sections}
    </body></html>"""


def run_caption_report():
    """벤치마크 계정 최신 3개 릴스 캡션+링크 수집 (Whisper 없음)"""
    print(f"\n📋  캡션 리포트 수집 시작...")
    account_results = []

    for account_url in BENCHMARK_ACCOUNTS:
        username = _url_to_username(account_url)
        print(f"\n[계정] @{username}")

        reels = get_reels_metadata(account_url, max_items=3)
        print(f"  → 수집된 릴스: {len(reels)}개")

        processed = []
        for reel in reels:
            caption = reel.get("caption", "")
            translated = ""
            if caption:
                try:
                    translated = translate_to_korean(caption[:500])
                except Exception as e:
                    translated = f"(번역 실패: {e})"

            thumbnail_text = ""
            if reel.get("thumbnail"):
                print(f"  🖼️  썸네일 OCR 시도...")
                thumbnail_text = try_ocr_thumbnail(reel["thumbnail"])

            processed.append({
                "url":            reel["url"],
                "thumbnail":      reel.get("thumbnail", ""),
                "caption":        caption,
                "translated":     translated,
                "thumbnail_text": thumbnail_text,
                "upload_date":    reel.get("upload_date", ""),
            })
            time.sleep(1)

        account_results.append((account_url, processed))
        time.sleep(3)

    if account_results:
        print("\n📬  캡션 리포트 이메일 발송 중...")
        subject = f"📋 벤치마크 캡션 리포트 — {datetime.now().strftime('%Y.%m.%d')}"
        html = build_caption_report_html(account_results)
        send_gmail(subject, html)
        print("✅  리포트 발송 완료!")
    else:
        print("\n수집된 릴스 없음")


def main():
    os.makedirs(TEMP_DIR, exist_ok=True)

    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    # 날짜 지정: python3 reels_translator.py --monitor --date 20260407
    target_date = None
    if "--date" in sys.argv:
        idx = sys.argv.index("--date")
        if idx + 1 < len(sys.argv):
            target_date = sys.argv[idx + 1]

    # --benchmark 모드는 Whisper 불필요
    if mode == "--benchmark":
        run_caption_report()
        return

    print("🔄  Whisper 모델 로딩 중...")
    model = whisper.load_model(WHISPER_MODEL)
    print(f"✅  Whisper '{WHISPER_MODEL}' 모델 준비 완료")

    if mode in ("all", "--report"):
        run_report(model)

    if mode in ("all", "--monitor"):
        run_monitor(model, target_date)


if __name__ == "__main__":
    main()
