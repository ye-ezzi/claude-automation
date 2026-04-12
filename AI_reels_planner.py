"""
AI/콘텐츠 릴스 + 피드 플래너 — 매일 오전 9시 자동 실행
=====================================================
STEP 1. Google Sheets에서 AI/디자인 콘텐츠 패턴 수집
STEP 2. 오늘의 AI툴 / 디자인 / 크리에이터 트렌드 웹 서치
STEP 3. Claude API로 릴스 아이디어 20개 생성
STEP 4. Claude API로 피드(카드뉴스) 아이디어 20개 생성
STEP 5. Gmail로 자동 발송 (실패 시 파일 저장)

필요 패키지:
  pip install anthropic requests ddgs
"""

import os
import re
import json
import time
import smtplib
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import anthropic

# .env 파일 로드
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

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

OUTPUT_DIR   = os.path.expanduser("~/reels_outputs")
HISTORY_FILE = os.path.join(OUTPUT_DIR, "ai_history.json")

# ── 폴백 패턴 (시트 접근 실패 시) ──────────────────────
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

ACCOUNT_DNA = """## 계정 DNA
- **타겟:** 20-30대 디자이너, 크리에이터, 프리랜서
- **주제:** AI 툴 & 워크플로우 / AI 디자인 / 콘텐츠 전략 / 프리랜서 비즈니스 / 생산성 해킹
- **톤앤매너:** 친절한 선배 느낌 — 따뜻하고 실용적, "몰랐지?" 모먼트 풍부, 절대 설교하지 않음
- **훅 스타일:** 팁 선행형, 호기심 유발형, 공감형 — 항상 따뜻하고 직접적
- **피해야 할 것:** 이론적인 내용, 비싼 장비/팀이 필요한 아이디어, 실행 불가능한 막연한 조언"""


# ══════════════════════════════════════════
# STEP 1 — Google Sheets 데이터 수집
# ══════════════════════════════════════════

def fetch_sheet_data():
    print("📊 [STEP 1] Google Sheets 데이터 수집 중...")
    try:
        resp = requests.get(SHEETS_URL, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])

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

# RSS 피드 소스 (카테고리별 최신 뉴스)
_AI_RSS_SOURCES = {
    "AI 툴 & 생산성": [
        "https://techcrunch.com/category/artificial-intelligence/feed/",
        "https://venturebeat.com/category/ai/feed/",
    ],
    "디자인 & 크리에이티브": [
        "https://www.theverge.com/rss/index.xml",
        "https://www.creativebloq.com/rss",
    ],
    "크리에이터 이코노미": [
        "https://www.socialmediatoday.com/rss.xml",
        "https://later.com/blog/feed/",
    ],
}

# DuckDuckGo 보조 쿼리 (RSS 실패 시, 최근 1주일 필터)
_AI_DDGS_QUERIES = {
    "AI 툴 & 생산성":     "new AI tools launch productivity app this week",
    "디자인 & 크리에이티브": "AI design tools Figma Canva Midjourney update this week",
    "크리에이터 이코노미":   "Instagram Reels creator monetization trends this week",
}

def _fetch_rss(url, max_items=4):
    """RSS 피드에서 최신 기사 제목+요약 가져오기"""
    try:
        resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        items = []
        for item in root.findall('.//item')[:max_items]:
            title   = (item.findtext('title') or '').strip()
            desc    = (item.findtext('description') or item.findtext('summary') or '').strip()
            desc    = re.sub(r'<[^>]+>', '', desc)[:200]
            link    = (item.findtext('link') or '').strip()
            if title:
                items.append({"title": title, "snippet": desc, "url": link})
        return items
    except Exception:
        return []

def search_trends():
    print("\n🔍 [STEP 2] 오늘의 트렌드 수집 중...")

    trends = {cat: [] for cat in _AI_RSS_SOURCES}

    # 1순위: RSS 피드
    for cat, feeds in _AI_RSS_SOURCES.items():
        for feed_url in feeds:
            items = _fetch_rss(feed_url)
            trends[cat].extend(items)
            if len(trends[cat]) >= 3:
                break
        if trends[cat]:
            print(f"  → {cat}: RSS {len(trends[cat])}개 수집")

    # 2순위: RSS 부족한 카테고리는 DuckDuckGo (최근 1주일)
    missing = [cat for cat, items in trends.items() if len(items) < 2]
    if missing:
        try:
            from ddgs import DDGS
            ddgs_client = DDGS()
            for cat in missing:
                query = _AI_DDGS_QUERIES[cat]
                results = ddgs_client.text(query, max_results=3, timelimit='w')
                for r in results:
                    trends[cat].append({
                        "title":   r.get("title", ""),
                        "snippet": r.get("body", "")[:200],
                        "url":     r.get("href", ""),
                    })
                print(f"  → {cat}: DuckDuckGo {len(trends[cat])}개 수집")
                time.sleep(1.2)
        except Exception as e:
            print(f"  ⚠️  웹 서치 실패 ({e}) → 기본 트렌드 사용")

    # 3순위: 여전히 비어있는 카테고리는 폴백 데이터
    fallback = {
        "AI 툴 & 생산성": [
            {"title": "Claude AI 최신 업데이트", "snippet": "Anthropic의 Claude가 새로운 기능을 출시했습니다.", "url": ""},
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
    for cat in trends:
        if not trends[cat]:
            trends[cat] = fallback[cat]
            print(f"  → {cat}: 폴백 데이터 사용")

    return trends


# ══════════════════════════════════════════
# 다양성 엔진 — 요일 테마 + 히스토리 회피
# ══════════════════════════════════════════

def get_daily_theme(weekday: int) -> dict:
    """요일(0=월 ~ 6=일)에 따라 오늘의 콘텐츠 각도 반환"""
    themes = {
        0: {"name": "🛠️ 툴 입문의 날",      "instruction": "처음 AI 툴을 접하는 완전 초보자 기준으로 기초부터 설명하는 콘텐츠에 집중하세요. '이런 게 있었어?' 반응을 유도하세요."},
        1: {"name": "⚡ 실전 활용의 날",     "instruction": "당장 오늘 써먹을 수 있는 구체적 활용법과 워크플로우에 집중하세요. 단계별 실습 중심으로."},
        2: {"name": "📊 비교·분석의 날",     "instruction": "툴 vs 툴, 방법 A vs 방법 B, 전/후 비교에 집중하세요. 데이터와 수치로 차이를 보여주세요."},
        3: {"name": "💡 창의 아이디어의 날", "instruction": "예상 밖의 색다른 AI 활용법, '이렇게도 쓸 수 있어?' 반응을 유도하는 창의적 아이디어에 집중하세요."},
        4: {"name": "📈 성장·수익화의 날",   "instruction": "크리에이터 성장, AI로 수익 창출, 프리랜서 비즈니스 확장에 집중하세요. 실제 사례와 수치 강조."},
        5: {"name": "🔥 이번 주 트렌드의 날","instruction": "이번 주 화제가 된 AI 신기능, 업데이트, 화제의 사용 사례에 집중하세요. 타이밍이 핵심."},
        6: {"name": "💬 소통·참여의 날",     "instruction": "팔로워 참여를 최대화하는 질문형·공감형 콘텐츠에 집중하세요. 댓글, DM, 저장을 이끌어내는 포맷."},
    }
    return themes[weekday]


def load_recent_titles(days: int = 21) -> list:
    """최근 N일 치 아이디어 제목 로드 (중복 방지용)"""
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, encoding="utf-8") as f:
            history = json.load(f)
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        recent = []
        for date, titles in history.items():
            if date >= cutoff:
                recent.extend(titles)
        return recent
    except Exception:
        return []


def save_titles_to_history(reels_output: str, feed_output: str):
    """생성된 아이디어 제목을 히스토리 파일에 저장"""
    today = datetime.now().strftime("%Y-%m-%d")
    titles = re.findall(r'\*\*아이디어 제목:\*\*\s*(.+)', reels_output + feed_output)
    if not titles:
        return
    history = {}
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            pass
    history[today] = [t.strip() for t in titles]
    # 30일 이전 데이터 자동 정리
    cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    history = {k: v for k, v in history.items() if k >= cutoff}
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    print(f"  📝 히스토리 저장: {len(titles)}개 제목 → {HISTORY_FILE}")


# ══════════════════════════════════════════
# STEP 3 — 릴스 아이디어 20개 생성
# ══════════════════════════════════════════

def build_reels_prompt(patterns: dict, trends: dict, theme: dict, recent_titles: list) -> str:
    today = datetime.now().strftime("%Y년 %m월 %d일")

    thumbnails = patterns.get("thumbnail", FALLBACK_PATTERNS["thumbnail"])[:8]
    hooks_3sec = patterns.get("hook_3sec", [])[:5]
    hooks_copy = patterns.get("hook_copy", [])[:5]
    captions   = patterns.get("caption",   FALLBACK_PATTERNS["caption"])[:4]

    trend_lines = []
    for cat, items in trends.items():
        trend_lines.append(f"\n**{cat}:**")
        for item in items:
            trend_lines.append(f"  - {item['title']}: {item['snippet'][:120]}")

    week_num = datetime.now().isocalendar()[1]
    avoid_block = (
        "\n".join(f"- {t}" for t in recent_titles[:50])
        if recent_titles else "- (첫 실행 — 제한 없음)"
    )

    return f"""당신은 10년 경력의 콘텐츠 디렉터입니다. 오늘({today}, {week_num}주차) AI & 크리에이티브 도구 인스타그램 계정을 위한 릴스 아이디어 20개를 생성해주세요.

{ACCOUNT_DNA}

## 오늘의 테마: {theme['name']}
{theme['instruction']}
→ 오늘 20개 아이디어의 각도, 접근법, 포맷을 이 테마 중심으로 조율하세요.

## 최근 21일 다룬 주제 (반드시 피하거나 완전히 다른 각도로)
{avoid_block}

## 실제 시트 패턴
**썸네일 문구 패턴:**
{chr(10).join(f"- {t}" for t in thumbnails)}

**첫 3초 훅 패턴:**
{chr(10).join(f"- {h}" for h in hooks_3sec) if hooks_3sec else "- (시트 데이터 없음 → 폴백 참고)"}

**후킹 멘트:**
{chr(10).join(f"- {h}" for h in hooks_copy) if hooks_copy else "- (시트 데이터 없음 → 폴백 참고)"}

**캡션 구조:**
{chr(10).join(f"- {c}" for c in captions)}

## 오늘의 트렌드
{"".join(trend_lines)}

## 아이디어 20개 생성 규칙
- 최소 6개: 특정 AI 툴/워크플로우 (GPT, Gemini, Canva AI, Midjourney, Firefly 등 툴명 반드시 명시)
- 최소 4개: AI × 디자인 (이미지 생성, 디자인 자동화, 브랜드킷, 목업 생성 등)
- 최소 4개: 프리랜서 실전 (가격 책정, 클라이언트 관리, 포트폴리오, 제안서 작성)
- 최소 3개: 콘텐츠 제작 / 인스타그램 성장 팁
- 나머지 3개: 오늘 트렌드 반응형

## 출력 형식 (정확히 이 형식, 20개 모두)

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


def generate_reels(patterns: dict, trends: dict, client: anthropic.Anthropic, theme: dict, recent_titles: list) -> str:
    print("\n🤖 [STEP 3] 릴스 아이디어 20개 생성 중...")
    prompt = build_reels_prompt(patterns, trends, theme, recent_titles)

    text = ""
    with client.messages.stream(
        model="claude-opus-4-6",
        max_tokens=8000,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for chunk in stream.text_stream:
            text += chunk
            print(chunk, end="", flush=True)

    print("\n  ✅ 릴스 아이디어 생성 완료")
    return text


# ══════════════════════════════════════════
# STEP 4 — 피드(카드뉴스) 아이디어 20개 생성
# ══════════════════════════════════════════

def build_feed_prompt(patterns: dict, trends: dict, theme: dict, recent_titles: list) -> str:
    today = datetime.now().strftime("%Y년 %m월 %d일")
    week_num = datetime.now().isocalendar()[1]
    avoid_block = (
        "\n".join(f"- {t}" for t in recent_titles[:50])
        if recent_titles else "- (첫 실행 — 제한 없음)"
    )

    trend_lines = []
    for cat, items in trends.items():
        trend_lines.append(f"\n**{cat}:**")
        for item in items:
            trend_lines.append(f"  - {item['title']}: {item['snippet'][:120]}")

    return f"""당신은 10년 경력의 콘텐츠 디렉터입니다. 오늘({today}, {week_num}주차) AI & 크리에이티브 도구 인스타그램 계정을 위한 피드(카드뉴스/캐러셀) 아이디어 20개를 생성해주세요.

{ACCOUNT_DNA}

## 오늘의 테마: {theme['name']}
{theme['instruction']}
→ 오늘 20개 아이디어의 각도, 접근법, 포맷을 이 테마 중심으로 조율하세요.

## 최근 21일 다룬 주제 (반드시 피하거나 완전히 다른 각도로)
{avoid_block}

## 오늘의 트렌드
{"".join(trend_lines)}

## 피드 아이디어 20개 생성 규칙
- 최소 6개: 특정 AI 툴/워크플로우 (툴명 반드시 명시)
- 최소 4개: AI × 디자인 (이미지 생성, 디자인 자동화 등)
- 최소 4개: 프리랜서 실전 팁 (저장하고 싶은 정보성)
- 최소 3개: 콘텐츠 제작 / 인스타그램 성장
- 나머지 3개: 오늘 트렌드 반응형
- 체크리스트·비교표·단계별 가이드 형식 선호
- 커버 카드는 반드시 숫자 또는 질문으로 시작
- 댓글 키워드 DM 전략 20개 중 최소 5개 적용

## 출력 형식 (정확히 이 형식, 20개 모두)

---

**피드 아이디어 #N**

1. **아이디어 제목:** [짧고 명확한 제목]
2. **카드 구성:** [슬라이드 수 — 예: 5장, 7장. 최대 10장]
3. **커버 카드 카피:** [첫 번째 슬라이드 훅 문구. 한 줄로 시선 잡기. 숫자·질문·반전 중 하나 활용]
4. **슬라이드별 내용 요약:**
   - 1장: [커버 훅]
   - 2장: [본문 핵심 내용 1]
   - 3장: [본문 핵심 내용 2]
   - ...마지막 장: [정리 + CTA]
5. **디자인 방향:** [배경색 톤, 폰트 무드, 핵심 시각 요소 — 1-2줄]
6. **캡션 첫 줄:** [피드 캡션 첫 문장 — 검색 유입과 저장 유도. 댓글 키워드 CTA 적극 활용]

---

**중요 원칙:**
- 커버는 숫자 또는 질문으로 반드시 시작
- 댓글 키워드 CTA: "댓글에 'XX' 남겨주시면 자료 보내드립니다" 패턴 20개 중 최소 5개 적용
- 모든 아이디어는 스마트폰 + 무료 툴(Canva 등)로 제작 가능해야 함
- 저장율 높이는 체크리스트·비교표·단계별 가이드 형식 선호"""


def generate_feed(patterns: dict, trends: dict, client: anthropic.Anthropic, theme: dict, recent_titles: list) -> str:
    print("\n🤖 [STEP 4] 피드(카드뉴스) 아이디어 20개 생성 중...")
    prompt = build_feed_prompt(patterns, trends, theme, recent_titles)

    text = ""
    with client.messages.stream(
        model="claude-opus-4-6",
        max_tokens=8000,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for chunk in stream.text_stream:
            text += chunk
            print(chunk, end="", flush=True)

    print("\n  ✅ 피드 아이디어 생성 완료")
    return text


# ══════════════════════════════════════════
# STEP 5 — Gmail 발송
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
            link    = f'<a href="{url}" style="color:#1a1a1a;font-weight:bold;">{title}</a>' if url else f"<strong>{title}</strong>"
            html   += f'<li style="margin-bottom:8px;">{link}<br><span style="color:#666;font-size:12px;">{snippet}</span></li>'
        html += "</ul>"
    return html


def content_to_html(raw: str, icon: str, id_prefix: str) -> str:
    html = raw
    html = re.sub(r"\n---\n", '\n<hr style="border:none;border-top:1px solid #EBEBEB;margin:24px 0;">\n', html)
    html = re.sub(
        rf"\*\*({id_prefix} #\d+)\*\*",
        rf'<h3 style="color:#1a1a1a;font-size:16px;margin:20px 0 12px;">{icon} \1</h3>',
        html
    )
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = html.replace("\n", "<br>")
    return html


def build_email_html(sheet_success: bool, trends: dict, reels: str, feed: str) -> str:
    today_kr    = datetime.now().strftime("%Y년 %m월 %d일")
    now_str     = datetime.now().strftime("%Y년 %m월 %d일 %H:%M")
    data_status = "✅ 실시간 시트 데이터 반영" if sheet_success else "⚠️ 폴백 데이터 사용"

    return f"""<!DOCTYPE html>
<html><body style="font-family:'Apple SD Gothic Neo',Arial,sans-serif;max-width:760px;margin:auto;padding:24px;color:#1a1a1a;background:#fff;">

  <h2 style="color:#2D2D2D;border-bottom:3px solid #4A90D9;padding-bottom:10px;margin-bottom:20px;">
    🎬 AI/콘텐츠 — 릴스 20 + 피드 20 — {today_kr}
  </h2>

  <div style="background:#F0F7FF;border-left:4px solid #4A90D9;padding:10px 16px;margin-bottom:28px;border-radius:4px;">
    <p style="margin:0;font-size:14px;"><strong>데이터 상태:</strong> {data_status}</p>
  </div>

  <h2 style="color:#2D2D2D;font-size:18px;border-bottom:2px solid #EBEBEB;padding-bottom:8px;margin-bottom:16px;">
    📈 오늘의 트렌드
  </h2>
  <div style="margin-bottom:36px;">{build_trend_html(trends)}</div>

  <h2 style="color:#2D2D2D;font-size:18px;border-bottom:2px solid #4A90D9;padding-bottom:8px;margin-bottom:16px;">
    🎬 릴스 아이디어 20개
  </h2>
  <div style="line-height:1.8;font-size:14px;margin-bottom:48px;">
    {content_to_html(reels, "🎬", "아이디어")}
  </div>

  <h2 style="color:#2D2D2D;font-size:18px;border-bottom:2px solid #4A90D9;padding-bottom:8px;margin-bottom:16px;">
    🗂️ 피드(카드뉴스) 아이디어 20개
  </h2>
  <div style="line-height:1.8;font-size:14px;">
    {content_to_html(feed, "🗂️", "피드 아이디어")}
  </div>

  <p style="color:#bbb;font-size:11px;margin-top:40px;text-align:right;">
    자동 생성 — {now_str} | AI_reels_planner.py
  </p>

</body></html>"""


def send_gmail(subject: str, html_body: str):
    print("\n📬 [STEP 5] Gmail 발송 중...")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_ADDRESS
    msg["To"]      = TO_ADDRESS
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, TO_ADDRESS, msg.as_string())
    print("  ✅ 이메일 발송 완료!")


def save_fallback(reels: str, feed: str, today_str: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, f"reels-ai-{today_str}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# AI/콘텐츠 — {today_str}\n\n## 릴스 아이디어 20개\n\n")
        f.write(reels)
        f.write("\n\n## 피드(카드뉴스) 아이디어 20개\n\n")
        f.write(feed)
    print(f"  💾 폴백 저장 완료: {path}")


# ══════════════════════════════════════════
# 메인
# ══════════════════════════════════════════

def main():
    today_str = datetime.now().strftime("%Y-%m-%d")
    now       = datetime.now()
    theme     = get_daily_theme(now.weekday())
    week_num  = now.isocalendar()[1]

    print(f"\n{'='*55}")
    print(f"  🚀 AI 릴스+피드 플래너 시작 — {today_str}")
    print(f"  📅 오늘 테마: {theme['name']} (#{week_num}주차)")
    print(f"{'='*55}\n")

    if not ANTHROPIC_API_KEY:
        raise EnvironmentError("ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다.")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # 히스토리 로드 (중복 방지)
    recent_titles = load_recent_titles()
    if recent_titles:
        print(f"  🚫 최근 21일 회피 목록: {len(recent_titles)}개 제목 로드")

    patterns, sheet_success = fetch_sheet_data()
    trends  = search_trends()
    reels   = generate_reels(patterns, trends, client, theme, recent_titles)
    feed    = generate_feed(patterns, trends, client, theme, recent_titles)

    # 히스토리 저장 (다음 실행에서 중복 방지)
    save_titles_to_history(reels, feed)

    subject   = f"[AI/콘텐츠] 오늘의 릴스 20 + 피드 20 — {today_str} {theme['name']}"
    html_body = build_email_html(sheet_success, trends, reels, feed)

    try:
        send_gmail(subject, html_body)
    except Exception as e:
        print(f"  ❌ Gmail 발송 실패: {e} → 파일 저장으로 대체")
        save_fallback(reels, feed, today_str)

    print(f"\n{'='*55}")
    print("  ✅ AI 릴스+피드 플래너 완료!")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
