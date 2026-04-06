"""
인스타그램 릴스 플래너 — 매일 오전 9시 자동 실행
=====================================================
STEP 1. Google Sheets (Apps Script)에서 기존 콘텐츠 패턴 수집
STEP 2. 오늘의 AI/디자인/크리에이터 트렌드 웹 서치
STEP 3. Claude API로 릴스 아이디어 20개 생성
STEP 4. Gmail로 자동 발송 (실패 시 파일 저장)

필요 패키지:
  pip install anthropic requests duckduckgo-search
"""

import os
import json
import time
import smtplib
import requests
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import anthropic

# ══════════════════════════════════════════
# 설정
# ══════════════════════════════════════════

GMAIL_ADDRESS  = "lyj990701@gmail.com"
GMAIL_PASSWORD = "ugfj tqjf xecw wvkv"
TO_ADDRESS     = "lyj990701@gmail.com"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

SHEETS_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbxFx0hkilEV-wLasfiIyv_Zchzi7PQWa8_qvdDpg_hsc98v_QKK3CsiwT1mW9I_hewg"
    "/exec?action=readSheet&sheet=Posts"
)

OUTPUT_DIR = "/sessions/magical-blissful-bohr/mnt/outputs"

# 폴백 데이터 (시트 접근 실패 시)
FALLBACK_PATTERNS = {
    "thumbnail": [
        "Gemini 3 말도 안돼... 놀라운 활용사례 6가지 → 감탄 + 숫자형",
        "당장 써먹을 수 있는 나노바나나 프롬프트 7선 → 즉시활용 + 숫자형",
        "고퀄리티 AI 이미지 비결? 프롬프트에 '이것' 넣어봐! → 질문 + 행동유도형",
        "나노바나나의 강적? GPT Image가 달라졌어요. → 비교/충격형",
        "나노바나나 프로 천재들은 이렇게 씁니다 1편 → 내부자팁 + 시리즈형",
        "나노 바나나 모르면 안되는 기능 → 모르면 손해형",
    ],
    "caption": [
        "오프닝: 공감/감탄 문장 (역대급 업데이트죠?, 요즘 화제인 X...)",
        "본문: 핵심 팁 1-2줄",
        "CTA: 댓글에 'OO' 남겨주시면 자료 보내드립니다!, 팔로우 후 댓글에 키워드 남기면 DM",
    ],
}


# ══════════════════════════════════════════
# STEP 1 — Google Sheets 데이터 수집
# ══════════════════════════════════════════

def fetch_sheet_data():
    """Google Apps Script URL에서 시트 데이터 가져와 AI/디자인 행만 필터링"""
    print("📊 [STEP 1] Google Sheets 데이터 수집 중...")
    try:
        resp = requests.get(SHEETS_URL, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])

        # AI/디자인 관련 행만 필터링
        filtered = [
            r for r in results
            if "AI" in str(r.get("분야", "")) or "디자인" in str(r.get("분야", ""))
        ]
        print(f"  → 전체 {len(results)}행 중 AI/디자인 {len(filtered)}행 필터링")

        patterns = {
            "thumbnail": [r.get("썸네일 문구", "") for r in filtered if r.get("썸네일 문구")],
            "hook_3sec": [r.get("첫 3초 훅", "")   for r in filtered if r.get("첫 3초 훅")],
            "hook_copy": [r.get("후킹 멘트", "")    for r in filtered if r.get("후킹 멘트")],
            "caption":   [r.get("캡션", "")         for r in filtered if r.get("캡션")],
        }
        print("  ✅ 실시간 시트 데이터 반영 완료")
        return patterns, True

    except Exception as e:
        print(f"  ⚠️  시트 접근 실패 ({e}) → 폴백 데이터 사용")
        return FALLBACK_PATTERNS, False


# ══════════════════════════════════════════
# STEP 2 — 오늘의 트렌드 수집
# ══════════════════════════════════════════

def search_trends():
    """duckduckgo-search로 오늘의 AI/디자인/크리에이터 트렌드 수집"""
    print("\n🔍 [STEP 2] 오늘의 트렌드 수집 중...")

    categories = {
        "AI 툴 & 생산성":    "AI tools productivity new launch update site:techcrunch.com OR site:theverge.com OR site:venturebeat.com",
        "디자인 & 크리에이티브": "Canva AI Midjourney Figma Adobe Firefly design tools trending update",
        "크리에이터 이코노미":  "Instagram Reels creator monetization freelance market trends",
    }
    trends = {cat: [] for cat in categories}

    try:
        from duckduckgo_search import DDGS
        ddgs = DDGS()

        for cat, query in categories.items():
            results = ddgs.text(query, max_results=3)
            for r in results:
                trends[cat].append({
                    "title":   r.get("title", ""),
                    "snippet": r.get("body", "")[:200],
                    "url":     r.get("href", ""),
                })
            print(f"  → {cat}: {len(trends[cat])}개 수집")
            time.sleep(1.2)  # 과도한 요청 방지

    except Exception as e:
        print(f"  ⚠️  웹 서치 실패 ({e}) → 기본 트렌드 사용")
        trends = {
            "AI 툴 & 생산성": [
                {"title": "Claude AI 최신 업데이트", "snippet": "Anthropic의 Claude가 새로운 기능을 출시했습니다. 크리에이터들 사이에서 화제입니다.", "url": ""},
                {"title": "GPT-4o 이미지 생성 화제", "snippet": "ChatGPT의 이미지 생성 기능이 디자이너들의 워크플로우를 바꾸고 있습니다.", "url": ""},
            ],
            "디자인 & 크리에이티브": [
                {"title": "Canva AI Magic Studio 업데이트", "snippet": "Canva의 AI 기능이 디자이너들의 작업 속도를 혁신적으로 개선합니다.", "url": ""},
                {"title": "Midjourney 신기능 출시", "snippet": "Midjourney의 새 버전이 더욱 정교한 이미지를 생성합니다.", "url": ""},
            ],
            "크리에이터 이코노미": [
                {"title": "Instagram Reels 수익화 확대", "snippet": "인스타그램이 릴스 크리에이터를 위한 수익화 옵션을 확대합니다.", "url": ""},
                {"title": "프리랜서 AI 활용 트렌드", "snippet": "프리랜서들이 AI 도구로 업무 효율을 높이고 있습니다.", "url": ""},
            ],
        }

    return trends


# ══════════════════════════════════════════
# STEP 3 — Claude API로 아이디어 20개 생성
# ══════════════════════════════════════════

def build_prompt(patterns: dict, trends: dict) -> str:
    today = datetime.now().strftime("%Y년 %m월 %d일")

    # 패턴 요약 텍스트
    thumbnails = patterns.get("thumbnail", FALLBACK_PATTERNS["thumbnail"])[:8]
    hooks_3sec = patterns.get("hook_3sec", [])[:5]
    hooks_copy = patterns.get("hook_copy", [])[:5]
    captions   = patterns.get("caption",   FALLBACK_PATTERNS["caption"])[:4]

    pattern_section = f"""## 실제 시트에서 추출한 콘텐츠 패턴

**썸네일 문구 패턴:**
{chr(10).join(f"- {t}" for t in thumbnails)}

**첫 3초 훅 패턴:**
{chr(10).join(f"- {h}" for h in hooks_3sec) if hooks_3sec else "- (시트 데이터 없음 → 폴백 참고)"}

**후킹 멘트:**
{chr(10).join(f"- {h}" for h in hooks_copy) if hooks_copy else "- (시트 데이터 없음 → 폴백 참고)"}

**캡션 구조:**
{chr(10).join(f"- {c}" for c in captions)}"""

    # 트렌드 요약 텍스트
    trend_lines = []
    for cat, items in trends.items():
        trend_lines.append(f"\n**{cat}:**")
        for item in items:
            trend_lines.append(f"  - {item['title']}: {item['snippet'][:120]}")
    trend_section = "\n".join(trend_lines)

    return f"""당신은 10년 경력의 콘텐츠 디렉터입니다. 오늘({today}) AI & 크리에이티브 도구 인스타그램 계정을 위한 릴스 아이디어 20개를 생성해주세요.

## 계정 DNA
- **타겟:** 20-30대 디자이너, 크리에이터, 프리랜서
- **주제:** AI 툴 & 워크플로우 / AI 디자인 / 콘텐츠 전략 / 프리랜서 비즈니스 / 생산성 해킹
- **톤앤매너:** 친절한 선배 느낌 — 따뜻하고 실용적, "몰랐지?" 모먼트 풍부, 절대 설교하지 않음
- **훅 스타일:** 팁 선행형, 호기심 유발형, 공감형 — 항상 따뜻하고 직접적

{pattern_section}

## 오늘의 트렌드
{trend_section}

## 아이디어 20개 생성 규칙
- 최소 6개: 특정 AI 툴/워크플로우 (GPT, Gemini, Canva AI, Midjourney, Firefly 등 툴명 반드시 명시)
- 최소 4개: AI × 디자인 (이미지 생성, 디자인 자동화, 브랜드킷, 목업 생성 등)
- 최소 4개: 프리랜서 실전 (가격 책정, 클라이언트 관리, 포트폴리오, 제안서 작성)
- 최소 3개: 콘텐츠 제작 / 인스타그램 성장 팁
- 나머지 3개: 오늘 트렌드 반응형 (위 트렌드 데이터 기반)

## 출력 형식 (정확히 이 형식을 따를 것, 20개 모두)

---

**아이디어 #N**

1. **아이디어 제목:** [짧고 강렬한 제목]
2. **후킹 카피 (첫 3초):** [스크롤 멈추게 하는 한 문장 — 따뜻하고 직접적이며 즉시 유용함]
3. **촬영 연출:** [구체적인 장면 묘사 — 화면에 무엇이 보이는지, 동작, 텍스트 오버레이. 스마트폰만 사용.]
4. **본문 카피 요약:** [2-4문장. 팁 먼저. 실용적, 군더더기 없이. 선배 말투로.]
5. **CTA:** [한 줄. 적절하면 "댓글에 'OOO' 남겨주시면 자료 보내드립니다!" 패턴 적용.]

---

**중요 원칙:**
- 썸네일 패턴: 숫자형 / 질문형 / 비교·충격형 / 내부자팁형 / "모르면 손해"형 골고루 활용
- 모든 아이디어는 스마트폰만으로 즉시 촬영 가능해야 함
- 훅은 강의 느낌 X, 친구가 귀띔해주는 느낌으로
- 캡션 오프닝은 공감 또는 감탄 → 핵심 팁 → CTA 순서"""


def generate_ideas(patterns: dict, trends: dict) -> str:
    """Claude API (streaming)로 릴스 아이디어 20개 생성"""
    print("\n🤖 [STEP 3] Claude API로 릴스 아이디어 생성 중...")

    if not ANTHROPIC_API_KEY:
        raise EnvironmentError("ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다.")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = build_prompt(patterns, trends)

    ideas_text = ""
    with client.messages.stream(
        model="claude-opus-4-6",
        max_tokens=8000,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for text in stream.text_stream:
            ideas_text += text
            print(text, end="", flush=True)

    print("\n  ✅ 아이디어 생성 완료")
    return ideas_text


# ══════════════════════════════════════════
# STEP 4 — Gmail 발송
# ══════════════════════════════════════════

def build_trend_html(trends: dict) -> str:
    html = ""
    for cat, items in trends.items():
        html += f'<h3 style="color:#4A90D9;margin:16px 0 8px;font-size:15px;">{cat}</h3>'
        html += '<ul style="margin:0 0 8px;padding-left:20px;">'
        for item in items:
            title   = item.get("title", "")
            snippet = item.get("snippet", "")[:150]
            url     = item.get("url", "")
            if url:
                html += f'<li style="margin-bottom:8px;"><a href="{url}" style="color:#2D2D2D;font-weight:bold;">{title}</a><br><span style="color:#666;font-size:12px;">{snippet}</span></li>'
            else:
                html += f'<li style="margin-bottom:8px;"><strong>{title}</strong><br><span style="color:#666;font-size:12px;">{snippet}</span></li>'
        html += "</ul>"
    return html


def ideas_to_html(ideas_raw: str) -> str:
    """마크다운 아이디어 텍스트를 HTML로 변환"""
    import re

    html = ideas_raw

    # 구분선
    html = re.sub(r"\n---\n", '\n<hr style="border:none;border-top:1px solid #EBEBEB;margin:24px 0;">\n', html)

    # **아이디어 #N** → h3
    html = re.sub(
        r"\*\*(아이디어 #\d+)\*\*",
        r'<h3 style="color:#1a1a1a;font-size:16px;margin:20px 0 12px;">💡 \1</h3>',
        html
    )

    # **굵게** → <strong>
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)

    # 줄바꿈
    html = html.replace("\n", "<br>")

    return html


def build_email_html(sheet_success: bool, trends: dict, ideas: str) -> str:
    today_kr    = datetime.now().strftime("%Y년 %m월 %d일")
    now_str     = datetime.now().strftime("%Y년 %m월 %d일 %H:%M")
    data_status = "✅ 실시간 시트 데이터 반영" if sheet_success else "⚠️ 폴백 데이터 사용"

    return f"""<!DOCTYPE html>
<html><body style="font-family:'Apple SD Gothic Neo',Arial,sans-serif;max-width:720px;margin:auto;padding:24px;color:#1a1a1a;background:#fff;">

  <h2 style="color:#2D2D2D;border-bottom:3px solid #4A90D9;padding-bottom:10px;margin-bottom:20px;">
    🎬 AI/콘텐츠 릴스 아이디어 20개 — {today_kr}
  </h2>

  <div style="background:#F0F7FF;border-left:4px solid #4A90D9;padding:10px 16px;margin-bottom:28px;border-radius:4px;">
    <p style="margin:0;font-size:14px;"><strong>데이터 상태:</strong> {data_status}</p>
  </div>

  <h2 style="color:#2D2D2D;font-size:18px;border-bottom:2px solid #EBEBEB;padding-bottom:8px;margin-bottom:16px;">
    📈 오늘의 트렌드
  </h2>
  <div style="margin-bottom:36px;">
    {build_trend_html(trends)}
  </div>

  <h2 style="color:#2D2D2D;font-size:18px;border-bottom:2px solid #EBEBEB;padding-bottom:8px;margin-bottom:16px;">
    💡 오늘의 릴스 아이디어 20개
  </h2>
  <div style="line-height:1.8;font-size:14px;">
    {ideas_to_html(ideas)}
  </div>

  <p style="color:#bbb;font-size:11px;margin-top:40px;text-align:right;">
    자동 생성 — {now_str} | reels_planner.py
  </p>

</body></html>"""


def send_gmail(subject: str, html_body: str):
    """Gmail SMTP SSL로 발송"""
    print("\n📬 [STEP 4] Gmail 발송 중...")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_ADDRESS
    msg["To"]      = TO_ADDRESS
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, TO_ADDRESS, msg.as_string())
    print("  ✅ 이메일 발송 완료!")


def save_fallback(ideas: str, today_str: str):
    """Gmail 발송 실패 시 마크다운 파일로 저장"""
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
    except Exception:
        OUTPUT_DIR_LOCAL = os.path.expanduser("~/reels_outputs")
        os.makedirs(OUTPUT_DIR_LOCAL, exist_ok=True)
        path = os.path.join(OUTPUT_DIR_LOCAL, f"reels-ai-{today_str}.md")
    else:
        path = os.path.join(OUTPUT_DIR, f"reels-ai-{today_str}.md")

    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# AI/콘텐츠 릴스 아이디어 20개 — {today_str}\n\n")
        f.write(ideas)
    print(f"  💾 폴백 저장 완료: {path}")


# ══════════════════════════════════════════
# 메인
# ══════════════════════════════════════════

def main():
    today_str = datetime.now().strftime("%Y-%m-%d")
    print(f"\n{'='*55}")
    print(f"  🚀 릴스 플래너 시작 — {today_str}")
    print(f"{'='*55}\n")

    # STEP 1: 시트 데이터
    patterns, sheet_success = fetch_sheet_data()

    # STEP 2: 트렌드
    trends = search_trends()

    # STEP 3: 아이디어 생성
    ideas = generate_ideas(patterns, trends)

    # STEP 4: 발송
    subject  = f"[AI/콘텐츠 릴스] 오늘의 아이디어 20개 — {today_str}"
    html_body = build_email_html(sheet_success, trends, ideas)

    try:
        send_gmail(subject, html_body)
    except Exception as e:
        print(f"  ❌ Gmail 발송 실패: {e} → 파일 저장으로 대체")
        save_fallback(ideas, today_str)

    print(f"\n{'='*55}")
    print("  ✅ 릴스 플래너 완료!")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
