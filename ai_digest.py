"""
AI Content Daily Digest
========================
Instagram (Chrome cookie) + X (twscrape) → 중복제거 → 이메일 발송

사용 전 설치:
    pip install browser_cookie3 requests twscrape

환경변수 설정 (비밀번호):
    export GMAIL_APP_PASSWORD='앱비밀번호16자리'
    export INSTAGRAM_PASS='인스타비밀번호'  # 현재 미사용 (Chrome 쿠키 방식)

최초 1회 X 계정 등록:
    python ai_digest.py --setup-x

매일 실행:
    python ai_digest.py --ig-only
    또는 cron: 0 8 * * * cd /Users/comcom && source venv/bin/activate && GMAIL_APP_PASSWORD='...' python3 ai_digest.py --ig-only
"""

import asyncio
import json
import os
import smtplib
import argparse
import time
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# ──────────────────────────────────────────
# ① 설정 (여기만 수정하세요)
# ──────────────────────────────────────────

CONFIG = {
    # 인스타 계정 (Chrome 쿠키 방식이라 실제 로그인엔 미사용)
    "instagram_user": "sora_ater",
    "instagram_pass": os.environ.get("INSTAGRAM_PASS", ""),

    # 인스타 채널 (@ 제외)
    "instagram_channels": [
        "higgsfield.ai",
        "bywaviboy",
        "ai.trend.kr",
        "invideo.io",
        "vizznary",
        "elicoleman_",
        "digitalbynana",
        "stevenwommack",
        "why.cgi",
        "tumifnx",
        "anotherworldcore",
        "re4ee",
    ],

    # X 계정 (@ 제외)
    "x_accounts": [
        "hansonerere2",
        "designer_hyosin",
        "michelletliu",
        "0xInk_",
        "azed_ai",
        "Morph_VGart",
        "Salmaaboukarr",
        "OVolosin82152",
    ],

    # X 로그인용 계정 (twscrape용, --setup-x 로 등록)
    "x_scraper_accounts": [],

    # 수집 범위 (일)
    "days_back": 3,

    # 채널당 최대 게시물 수 (조회수 상위 N개)
    "max_per_channel": 3,

    # X 최소 좋아요 기준
    "min_x_likes": 10,

    # 이메일 설정
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 587,
    "sender_email": "lyj990701@gmail.com",
    "sender_password": os.environ.get("GMAIL_APP_PASSWORD", ""),
    "recipient_email": "lyj990701@gmail.com",

    # 중복 추적 파일 경로
    "sent_ids_path": "sent_ids.json",
}

# ──────────────────────────────────────────
# ② 중복 ID 관리
# ──────────────────────────────────────────

def load_sent_ids() -> dict:
    path = Path(CONFIG["sent_ids_path"])
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {"sent": {}}

def save_sent_ids(data: dict):
    with open(CONFIG["sent_ids_path"], "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def cleanup_old_ids(data: dict) -> dict:
    """7일 지난 ID 자동 삭제"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    data["sent"] = {
        k: v for k, v in data["sent"].items()
        if datetime.fromisoformat(v) > cutoff
    }
    return data

def is_new(post_id: str, sent_data: dict) -> bool:
    return post_id not in sent_data["sent"]

def mark_sent(post_id: str, sent_data: dict):
    sent_data["sent"][post_id] = datetime.now(timezone.utc).isoformat()

# ──────────────────────────────────────────
# ③ 인스타그램 스크래핑 (Chrome 쿠키 방식)
# ──────────────────────────────────────────

def scrape_instagram() -> list[dict]:
    try:
        import browser_cookie3
        import requests
    except ImportError:
        print("❌ browser_cookie3 미설치: pip install browser_cookie3 requests")
        return []

    try:
        cookies = browser_cookie3.chrome(domain_name='.instagram.com')
    except Exception as e:
        print(f"❌ Chrome 쿠키 로드 실패: {e}")
        return []

    session = requests.Session()
    session.cookies.update(cookies)
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "x-ig-app-id": "936619743392459",
        "Accept": "*/*",
    })

    def get_user_id(username):
        try:
            resp = session.get(
                f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}",
                timeout=15
            )
            if resp.status_code == 200:
                return resp.json()["data"]["user"]["id"]
        except Exception as e:
            print(f"  ⚠️ user_id 조회 실패: {e}")
        return None

    cutoff = datetime.now(timezone.utc) - timedelta(days=CONFIG["days_back"])
    results = []

    for channel in CONFIG["instagram_channels"]:
        print(f"📸 인스타 수집 중: @{channel}")
        try:
            user_id = get_user_id(channel)
            if not user_id:
                print(f"  ⚠️ {channel} user_id 없음")
                continue

            posts = []
            cursor = None
            done = False

            # 피드 수집
            while not done:
                params = {"count": 12, "user_id": user_id}
                if cursor:
                    params["max_id"] = cursor
                resp = session.get(
                    f"https://www.instagram.com/api/v1/feed/user/{user_id}/",
                    params=params, timeout=15
                )
                if resp.status_code != 200:
                    break
                data = resp.json()

                page_has_recent = False
                for item in data.get("items", []):
                    taken_at = item.get("taken_at", 0)
                    post_date = datetime.fromtimestamp(taken_at, tz=timezone.utc)
                    if post_date < cutoff:
                        continue  # 고정 게시물 등 오래된 것은 건너뜀
                    page_has_recent = True
                    is_video = item.get("media_type") == 2
                    views = item.get("view_count") or item.get("play_count") or 0
                    likes = item.get("like_count") or 0
                    shortcode = item.get("code", item.get("id", ""))
                    cap = item.get("caption") or {}
                    caption_text = cap.get("text", "") if isinstance(cap, dict) else ""
                    posts.append({
                        "id": f"ig_{shortcode}",
                        "platform": "instagram",
                        "channel": f"@{channel}",
                        "caption": caption_text[:200],
                        "views": views,
                        "likes": likes,
                        "url": f"https://www.instagram.com/p/{shortcode}/",
                        "date": post_date.strftime("%Y-%m-%d"),
                        "is_video": is_video,
                    })

                # 페이지 전체가 오래된 게시물이면 더 이상 페이지 없음
                if not page_has_recent:
                    done = True
                if not data.get("more_available") or not data.get("next_max_id"):
                    break
                cursor = data["next_max_id"]
                time.sleep(1)

            # 릴스 별도 수집 (clips API)
            reels_cursor = None
            reels_done = False
            while not reels_done:
                payload = {"target_user_id": user_id, "page_size": 12}
                if reels_cursor:
                    payload["max_id"] = reels_cursor
                r2 = session.post(
                    "https://www.instagram.com/api/v1/clips/user/",
                    data=payload, timeout=15
                )
                if r2.status_code != 200:
                    break
                rdata = r2.json()
                page_has_recent = False
                for item in rdata.get("items", []):
                    media = item.get("media", item)
                    taken_at = media.get("taken_at", 0)
                    post_date = datetime.fromtimestamp(taken_at, tz=timezone.utc)
                    if post_date < cutoff:
                        continue
                    page_has_recent = True
                    views = media.get("view_count") or media.get("play_count") or 0
                    likes = media.get("like_count") or 0
                    shortcode = media.get("code", media.get("id", ""))
                    cap = media.get("caption") or {}
                    caption_text = cap.get("text", "") if isinstance(cap, dict) else ""
                    pid = f"ig_{shortcode}"
                    if not any(p["id"] == pid for p in posts):
                        posts.append({
                            "id": pid,
                            "platform": "instagram",
                            "channel": f"@{channel}",
                            "caption": caption_text[:200],
                            "views": views,
                            "likes": likes,
                            "url": f"https://www.instagram.com/reel/{shortcode}/",
                            "date": post_date.strftime("%Y-%m-%d"),
                            "is_video": True,
                        })
                if not page_has_recent:
                    reels_done = True
                if not rdata.get("paging_info", {}).get("more_available"):
                    break
                reels_cursor = rdata.get("paging_info", {}).get("max_id")
                time.sleep(1)

            # 조회수 내림차순 정렬 후 상위 N개
            posts.sort(key=lambda p: p["views"], reverse=True)
            results.extend(posts[:CONFIG["max_per_channel"]])

        except Exception as e:
            print(f"  ⚠️ {channel} 실패: {e}")

    return results

# ──────────────────────────────────────────
# ④ X(트위터) 스크래핑
# ──────────────────────────────────────────

async def scrape_x_async() -> list[dict]:
    try:
        from twscrape import API, gather
    except ImportError:
        print("❌ twscrape 미설치: pip install twscrape")
        return []

    api = API()
    for acc in CONFIG["x_scraper_accounts"]:
        await api.pool.add_account(
            username=acc["username"],
            password=acc["password"],
            email=acc["email"],
            email_password=acc.get("email_password", acc["password"]),
        )
    await api.pool.login_all()

    cutoff = datetime.now(timezone.utc) - timedelta(days=CONFIG["days_back"])
    results = []

    for account in CONFIG["x_accounts"]:
        print(f"🐦 X 수집 중: @{account}")
        try:
            user = await api.user_by_login(account)
            if not user:
                print(f"  ⚠️ {account} 유저 없음")
                continue
            tweets = await gather(api.user_tweets(user.id, limit=20))
            posts = []
            for tweet in tweets:
                tweet_date = tweet.date.replace(tzinfo=timezone.utc)
                if tweet_date < cutoff:
                    continue
                if tweet.likeCount < CONFIG["min_x_likes"]:
                    continue
                posts.append({
                    "id": f"x_{tweet.id}",
                    "platform": "x",
                    "channel": f"@{account}",
                    "caption": tweet.rawContent[:300],
                    "views": tweet.viewCount or 0,
                    "likes": tweet.likeCount,
                    "url": f"https://x.com/{account}/status/{tweet.id}",
                    "date": tweet_date.strftime("%Y-%m-%d"),
                    "is_video": False,
                })
                if len(posts) >= CONFIG["max_per_channel"]:
                    break
            results.extend(posts)
        except Exception as e:
            print(f"  ⚠️ {account} 실패: {e}")

    return results

def scrape_x() -> list[dict]:
    return asyncio.run(scrape_x_async())

# ──────────────────────────────────────────
# ⑤ 이메일 HTML 생성
# ──────────────────────────────────────────

def build_email_html(posts: list[dict]) -> str:
    today = datetime.now().strftime("%Y년 %m월 %d일")
    ig_posts = [p for p in posts if p["platform"] == "instagram"]
    x_posts  = [p for p in posts if p["platform"] == "x"]

    def post_card(p: dict) -> str:
        emoji = "📸" if p["platform"] == "instagram" else "🐦"
        views_str = f"👁 {p['views']:,}" if p['views'] else ""
        likes_str = f"❤️ {p['likes']:,}"
        stats = " · ".join(filter(None, [views_str, likes_str]))
        caption = p["caption"].replace("\n", " ").strip()
        if len(caption) > 150:
            caption = caption[:150] + "..."
        return f"""
        <div style="border:1px solid #e5e7eb;border-radius:12px;padding:16px;margin-bottom:12px;background:#fff;">
          <div style="font-size:13px;color:#6b7280;margin-bottom:6px;">
            {emoji} <strong>{p['channel']}</strong> · {p['date']} · {stats}
          </div>
          <div style="font-size:14px;color:#111827;line-height:1.6;margin-bottom:10px;">
            {caption}
          </div>
          <a href="{p['url']}" style="font-size:13px;color:#6366f1;text-decoration:none;font-weight:600;">
            → 원본 보기
          </a>
        </div>
        """

    def section(title: str, items: list[dict]) -> str:
        if not items:
            return ""
        cards = "".join(post_card(p) for p in items)
        return f"""
        <h2 style="font-size:16px;font-weight:700;color:#374151;margin:24px 0 12px;
                   padding-bottom:8px;border-bottom:2px solid #e5e7eb;">
          {title} ({len(items)}개)
        </h2>
        {cards}
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family:-apple-system,sans-serif;max-width:640px;margin:0 auto;
                 padding:24px;background:#f9fafb;color:#111827;">
      <div style="background:#6366f1;border-radius:16px;padding:24px;margin-bottom:24px;text-align:center;">
        <h1 style="color:#fff;font-size:22px;margin:0;">🤖 AI 콘텐츠 데일리 다이제스트</h1>
        <p style="color:#c7d2fe;margin:8px 0 0;font-size:14px;">{today} · 총 {len(posts)}개 콘텐츠</p>
      </div>
      {section("📸 Instagram", ig_posts)}
      {section("🐦 X (Twitter)", x_posts)}
      {"<p style='text-align:center;color:#9ca3af;font-size:12px;margin-top:32px;'>최근 3일 이내 · 채널당 조회수 상위 3개</p>" if posts else
       "<p style='text-align:center;color:#9ca3af;'>오늘은 새로운 콘텐츠가 없어요 🙂</p>"}
    </body>
    </html>
    """

# ──────────────────────────────────────────
# ⑥ 이메일 발송
# ──────────────────────────────────────────

def send_email(html: str, post_count: int):
    today = datetime.now().strftime("%m/%d")
    subject = f"[AI 다이제스트] {today} · {post_count}개 콘텐츠"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = CONFIG["sender_email"]
    msg["To"] = CONFIG["recipient_email"]
    msg.attach(MIMEText(html, "html", "utf-8"))
    with smtplib.SMTP(CONFIG["smtp_host"], CONFIG["smtp_port"]) as server:
        server.starttls()
        server.login(CONFIG["sender_email"], CONFIG["sender_password"])
        server.sendmail(CONFIG["sender_email"], CONFIG["recipient_email"], msg.as_string())
    print(f"✅ 이메일 발송 완료: {subject}")

# ──────────────────────────────────────────
# ⑦ 메인 실행
# ──────────────────────────────────────────

async def setup_x():
    from twscrape import API
    api = API()
    print("X 계정 정보를 입력하세요")
    username = input("X 아이디: ").strip()
    password = input("비밀번호: ").strip()
    email    = input("가입 이메일: ").strip()
    await api.pool.add_account(username, password, email, password)
    await api.pool.login_all()
    print("✅ X 계정 등록 완료!")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--setup-x", action="store_true")
    parser.add_argument("--ig-only",  action="store_true")
    parser.add_argument("--x-only",   action="store_true")
    parser.add_argument("--dry-run",  action="store_true")
    args = parser.parse_args()

    if args.setup_x:
        asyncio.run(setup_x())
        return

    print(f"\n{'='*50}")
    print(f"🚀 AI 다이제스트 시작 | {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}\n")

    sent_data = load_sent_ids()
    sent_data = cleanup_old_ids(sent_data)
    all_posts = []

    if not args.x_only:
        ig_posts = scrape_instagram()
        all_posts.extend(ig_posts)
        print(f"  → 인스타 수집: {len(ig_posts)}개\n")

    if not args.ig_only:
        x_posts = scrape_x()
        all_posts.extend(x_posts)
        print(f"  → X 수집: {len(x_posts)}개\n")

    new_posts = [p for p in all_posts if is_new(p["id"], sent_data)]
    print(f"✨ 신규 콘텐츠: {len(new_posts)}개 (전체 {len(all_posts)}개 중)")

    new_posts.sort(key=lambda p: p["views"] + p["likes"] * 10, reverse=True)
    html = build_email_html(new_posts)

    if args.dry_run:
        with open("digest_preview.html", "w") as f:
            f.write(html)
        print("📄 미리보기 저장: digest_preview.html")
        return

    send_email(html, len(new_posts))

    for p in new_posts:
        mark_sent(p["id"], sent_data)
    save_sent_ids(sent_data)
    print(f"\n✅ 완료! sent_ids.json 업데이트됨 ({len(sent_data['sent'])}개 누적)\n")

if __name__ == "__main__":
    main()
