"""
재테크 릴스 + 피드 플래너 — 매일 오전 9시 자동 실행
=====================================================
STEP 1. Google Sheets에서 기존 재테크 콘텐츠 패턴 수집
STEP 2. 오늘의 주식시장 / 부동산 / 재테크 트렌드 웹 서치
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
    "/exec"
)

OUTPUT_DIR   = os.path.expanduser("~/reels_outputs")
HISTORY_FILE = os.path.join(OUTPUT_DIR, "finance_history.json")

# ── 폴백 패턴 (시트 접근 실패 시) ──────────────────────
FALLBACK_PATTERNS = {
    "thumbnail": [
        "감탄 + 숫자 리스트: '~~ 말도 안돼... 놀라운 ~~사례 6가지' → 숫자로 구체성 부여",
        "즉시 실용성 + 숫자: '당장 써먹을 수 있는 ~~ 7선' → 즉각적 가치 강조",
        "질문 + 미스터리: '~~비결? 이것만 알면 됩니다!' → 호기심 유발",
        "FOMO형: '~~ 모르면 안되는 것' → 놓치는 것에 대한 두려움",
        "시리즈 + 벤치마킹: '천재들은 이렇게 합니다 1편' → 반복 방문 유도",
        "경쟁/비교 + 최신 뉴스: '~~의 강적? ~~ 달라졌어요.' → 트렌드 반응형",
    ],
    "caption": [
        "댓글 키워드 DM 전략: '팔로우 후 댓글에 XX 남겨주시면 자료를 보내드립니다!'",
        "공감형 고민 + 치트키: '왜 내 ~~만 이상하지...? 치트키 이 단어를 추가해보세요!'",
        "접근성 프레임: '누구나 ~~할 수 있는 팁!!' → 진입 장벽 낮추기",
        "질문으로 시작 + 극찬 + 정보 약속: '역대급 ~~조? 미친 활용 사례들을 소개합니다!'",
        "시리즈 예고 + 댓글 CTA: '1탄 💬 댓글에 XX 달면, 바로 복붙할 수 있게'",
    ],
}

ACCOUNT_DNA = """## 계정 DNA
- **타겟:**
  - 결혼을 준비하는 20-30대 커플 (맞벌이, 내집마련 저축, 함께 재무 계획)
  - 투자와 재테크를 막 시작하는 30대 입문자
- **주제:** 주식 기초 & 뉴스 / 부동산 & 주거 / 저축 & 예산 / 커플 재무 계획 / 투자 진입 시점
- **톤앤매너:** 논리적이고 스마트한 과장님 — 데이터 기반, 분석적, 가끔 드라이한 유머.
  연구 다 해놓고 핵심만 알려주는 스마트한 동료 같은 느낌. 절대 아래로 보지 않고, 항상 힘을 실어줌.
- **피해야 할 것:** 과도한 금융 전문 용어, 단기 부자되기 프레임, 검증 불가 주장, 큰 자본이 필요한 내용"""


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
            if any(k in str(r.get("분야", "")) for k in ["재테크", "경제", "투자", "부동산", "주식"])
        ]
        print(f"  → 전체 {len(results)}행 중 재테크 관련 {len(filtered)}행 필터링")

        patterns = {
            "thumbnail": [r.get("썸네일 문구", "") for r in filtered if r.get("썸네일 문구")],
            "hook_3sec": [r.get("첫 3초 훅", "")   for r in filtered if r.get("첫 3초 훅")],
            "hook_copy": [r.get("후킹 멘트", "")    for r in filtered if r.get("후킹 멘트")],
            "caption":   [r.get("캡션", "")         for r in filtered if r.get("캡션")],
            "good":      [r.get("좋은점", "")        for r in filtered if r.get("좋은점")],
            "bad":       [r.get("아쉬운점", "")      for r in filtered if r.get("아쉬운점")],
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
_FIN_RSS_SOURCES = {
    "주식시장": [
        "https://www.hankyung.com/feed/economy",
        "https://www.yna.co.kr/rss/economy.xml",
    ],
    "부동산 시장": [
        "https://www.hankyung.com/feed/realestate",
        "https://www.yna.co.kr/rss/realestate.xml",
    ],
    "재테크 입문·절약": [
        "https://www.hankyung.com/feed/finance",
        "https://www.mk.co.kr/rss/30100041/",
    ],
}

# DuckDuckGo 보조 쿼리 (RSS 실패 시, 최근 1주일 필터)
_FIN_DDGS_QUERIES = {
    "주식시장":        "Korea KOSPI stock market ETF interest rate this week",
    "부동산 시장":     "Korea apartment real estate jeonse market trend this week",
    "재테크 입문·절약": "Korea personal finance saving investing couples beginner this week",
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
    print("\n🔍 [STEP 2] 오늘의 재테크 트렌드 수집 중...")

    trends = {cat: [] for cat in _FIN_RSS_SOURCES}

    # 1순위: RSS 피드
    for cat, feeds in _FIN_RSS_SOURCES.items():
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
                query = _FIN_DDGS_QUERIES[cat]
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
        "주식시장": [
            {"title": "KOSPI 오늘 시장 동향", "snippet": "국내외 주요 지수 움직임과 투자자 관심 섹터가 화제입니다.", "url": ""},
            {"title": "미국 금리 결정 영향", "snippet": "연준 금리 결정이 국내 주식·채권 시장에 미치는 영향 분석.", "url": ""},
        ],
        "부동산 시장": [
            {"title": "서울 아파트 전세 시장 변화", "snippet": "전세가율과 매매가 변동 추이, 실수요자 주목 지역.", "url": ""},
            {"title": "청약 제도 변경 핵심 정리", "snippet": "청약 가점제·추첨제 변경 사항과 전략.", "url": ""},
        ],
        "재테크 입문·절약": [
            {"title": "ISA·IRP 절세 계좌 활용법", "snippet": "연말정산 환급을 위한 ISA, IRP 납입 전략이 인기입니다.", "url": ""},
            {"title": "커플 통장 쪼개기 트렌드", "snippet": "결혼 준비 커플들의 공동 저축 계좌 운영 방법이 화제.", "url": ""},
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
        0: {"name": "📚 기초 개념의 날",   "instruction": "재테크 입문자를 위한 용어 설명, 기초 개념, 입문 가이드에 집중하세요. '이걸 몰랐다니' 반응을 유도하세요."},
        1: {"name": "💑 커플·결혼의 날",   "instruction": "결혼 준비 커플의 재무 계획, 맞벌이 저축 전략, 신혼부부 돈 관리에 집중하세요. 커플이 함께 보는 콘텐츠."},
        2: {"name": "📊 데이터·수치의 날", "instruction": "통계, 수익률, 수치 비교, 데이터 기반 인사이트에 집중하세요. 숫자로 설득하는 콘텐츠."},
        3: {"name": "⚠️ 실수·주의의 날",  "instruction": "흔한 재테크 실수, 함정, 피해야 할 것들에 집중하세요. '이거 하면 안 돼요' 경각심 콘텐츠."},
        4: {"name": "🏠 부동산·청약의 날", "instruction": "부동산 실전 정보, 청약 전략, 전세 vs 매매, 전세사기 예방에 집중하세요."},
        5: {"name": "📈 주식·ETF의 날",    "instruction": "주식 투자 실전, ETF 선택법, 배당주, 포트폴리오 구성에 집중하세요. 초보자가 실제로 할 수 있는 것들."},
        6: {"name": "🎯 목표·습관의 날",   "instruction": "재테크 습관 형성, 목표 설정, 절약 루틴, 동기부여 콘텐츠에 집중하세요. 지속 가능한 실천."},
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

    thumbnails = patterns.get("thumbnail", FALLBACK_PATTERNS["thumbnail"])[:6]
    captions   = patterns.get("caption",   FALLBACK_PATTERNS["caption"])[:4]

    goods = patterns.get("good", [])[:8]
    bads  = patterns.get("bad",  [])[:8]

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
    feedback_block = ""
    if goods or bads:
        feedback_block = "\n## 과거 콘텐츠 피드백 (시트 기반)\n"
        if goods:
            feedback_block += "**잘 된 점 (이 방향으로 더):**\n"
            feedback_block += "\n".join(f"- {g}" for g in goods) + "\n"
        if bads:
            feedback_block += "**아쉬운 점 (이 실수 반복 금지):**\n"
            feedback_block += "\n".join(f"- {b}" for b in bads) + "\n"

    return f"""당신은 10년 경력의 재테크 콘텐츠 디렉터입니다. 오늘({today}, {week_num}주차) 재테크 인스타그램 계정을 위한 릴스 아이디어 20개를 생성해주세요.

{ACCOUNT_DNA}

## 오늘의 테마: {theme['name']}
{theme['instruction']}
→ 오늘 20개 아이디어의 각도, 접근법, 포맷을 이 테마 중심으로 조율하세요.

## 최근 21일 다룬 주제 (반드시 피하거나 완전히 다른 각도로)
{avoid_block}
{feedback_block}
## 실제 시트 패턴
**썸네일 훅 패턴 (이 키워드 톤·구조·길이를 최대한 유사하게 따라 쓸 것):**
{chr(10).join(f"- {t}" for t in thumbnails)}
→ 위 썸네일들의 공통 키워드, 말투, 숫자/질문/반전 패턴을 분석해서 오늘 아이디어 썸네일에 그대로 녹여주세요.

**캡션 패턴:**
{chr(10).join(f"- {c}" for c in captions)}

## 성과 데이터
- 댓글 키워드 CTA 포함 포스트: 4.9천 조회, 2천 댓글 (압도적)
- 숫자 리스트 썸네일: 조회수 2~3배
- 시리즈 포맷: 팔로우 전환율 높음

## 오늘의 트렌드
{"".join(trend_lines)}

## 아이디어 20개 생성 규칙
- 최소 6개: 커플 특화 (맞벌이 저축, 결혼 준비 재무, 함께하는 투자 등)
- 최소 6개: 주식시장 / 투자 기초 (ETF, 배당주, 분산투자 등)
- 최소 4개: 부동산 (전세 vs 매매, 청약, 전세사기 예방 등)
- 나머지 4개: 오늘 트렌드 반응형

## 출력 형식 (정확히 이 형식, 20개 모두)

---

**릴스 아이디어 #N**

1. **아이디어 제목:** [짧고 강렬한 제목]
2. **후킹 카피 (첫 3초):** [스크롤 멈추게 하는 한 문장. 결혼 준비 커플이나 투자 입문자에게 직접 말하는 느낌. 긴박하거나 개인적으로 와닿게.]
3. **촬영 연출:** [구체적인 장면 — 화면에 무엇이 보이는지, 소품, 프레이밍. 스마트폰만으로 가능.]
4. **본문 카피 요약:** [2-4문장. 가능하면 데이터 기반. 실용적이고 즉시 적용 가능.]
5. **CTA:** [한 줄. 댓글 키워드 DM 전략 적극 활용 — "댓글에 'XX' 남겨주시면 자료 보내드립니다"]

---

**중요 원칙:**
- 훅은 공감 기반, 현실적 — 공포 조장 X, 솔직하게 이해관계 전달
- FOMO 훅 / 숫자 리스트 / 댓글 키워드 CTA / 공감형 고민 패턴 골고루 활용
- 과장된 수익률 보장, 특정 종목 강추 절대 금지
- 모든 아이디어 스마트폰만으로 즉시 촬영 가능"""


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
    goods = patterns.get("good", [])[:8]
    bads  = patterns.get("bad",  [])[:8]
    avoid_block = (
        "\n".join(f"- {t}" for t in recent_titles[:50])
        if recent_titles else "- (첫 실행 — 제한 없음)"
    )
    feedback_block = ""
    if goods or bads:
        feedback_block = "\n## 과거 콘텐츠 피드백 (시트 기반)\n"
        if goods:
            feedback_block += "**잘 된 점 (이 방향으로 더):**\n"
            feedback_block += "\n".join(f"- {g}" for g in goods) + "\n"
        if bads:
            feedback_block += "**아쉬운 점 (이 실수 반복 금지):**\n"
            feedback_block += "\n".join(f"- {b}" for b in bads) + "\n"

    trend_lines = []
    for cat, items in trends.items():
        trend_lines.append(f"\n**{cat}:**")
        for item in items:
            trend_lines.append(f"  - {item['title']}: {item['snippet'][:120]}")

    return f"""당신은 10년 경력의 재테크 콘텐츠 디렉터입니다. 오늘({today}, {week_num}주차) 재테크 인스타그램 계정을 위한 피드(카드뉴스/캐러셀) 아이디어 20개를 생성해주세요.

{ACCOUNT_DNA}

## 오늘의 테마: {theme['name']}
{theme['instruction']}
→ 오늘 20개 아이디어의 각도, 접근법, 포맷을 이 테마 중심으로 조율하세요.

## 최근 21일 다룬 주제 (반드시 피하거나 완전히 다른 각도로)
{avoid_block}
{feedback_block}
## 오늘의 트렌드
{"".join(trend_lines)}

## 피드 아이디어 20개 생성 규칙
- 최소 6개: 커플 특화 (맞벌이 저축, 결혼 준비 재무, 함께하는 투자 등)
- 최소 6개: 주식시장 / 투자 기초
- 최소 4개: 부동산 (전세 vs 매매, 청약, 전세사기 예방 등)
- 나머지 4개: 오늘 트렌드 반응형
- 카드뉴스는 '저장하고 싶은 정보성' 콘텐츠 위주 — 체크리스트, 비교표, 단계별 가이드 형식 선호
- 커버 카드는 위 시트 썸네일 패턴의 키워드·말투를 참고해서 작성
- 캡션에 댓글 키워드 DM 전략 최소 5개 적용

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
- 커버는 숫자(몇 가지, 몇 %) 또는 질문으로 반드시 시작
- 댓글 키워드 CTA: "댓글에 'XX' 남겨주시면 PDF/자료 보내드립니다" 패턴 20개 중 최소 5개 적용
- 과장된 수익률 보장, 특정 종목 강추 절대 금지
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
        html += f'<h3 style="color:#2E7D32;margin:16px 0 8px;font-size:15px;">{cat}</h3>'
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

  <h2 style="color:#2D2D2D;border-bottom:3px solid #2E7D32;padding-bottom:10px;margin-bottom:20px;">
    💰 재테크 콘텐츠 — 릴스 20 + 피드 20 — {today_kr}
  </h2>

  <div style="background:#F1F8E9;border-left:4px solid #2E7D32;padding:10px 16px;margin-bottom:28px;border-radius:4px;">
    <p style="margin:0;font-size:14px;"><strong>데이터 상태:</strong> {data_status}</p>
  </div>

  <h2 style="color:#2D2D2D;font-size:18px;border-bottom:2px solid #EBEBEB;padding-bottom:8px;margin-bottom:16px;">
    📈 오늘의 재테크 트렌드
  </h2>
  <div style="margin-bottom:36px;">{build_trend_html(trends)}</div>

  <h2 style="color:#2D2D2D;font-size:18px;border-bottom:2px solid #2E7D32;padding-bottom:8px;margin-bottom:16px;">
    🎬 릴스 아이디어 20개
  </h2>
  <div style="line-height:1.8;font-size:14px;margin-bottom:48px;">
    {content_to_html(reels, "🎬", "릴스 아이디어")}
  </div>

  <h2 style="color:#2D2D2D;font-size:18px;border-bottom:2px solid #2E7D32;padding-bottom:8px;margin-bottom:16px;">
    🗂️ 피드(카드뉴스) 아이디어 20개
  </h2>
  <div style="line-height:1.8;font-size:14px;">
    {content_to_html(feed, "🗂️", "피드 아이디어")}
  </div>

  <p style="color:#bbb;font-size:11px;margin-top:40px;text-align:right;">
    자동 생성 — {now_str} | finance_reels_planner.py
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
    path = os.path.join(OUTPUT_DIR, f"reels-finance-{today_str}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# 재테크 콘텐츠 — {today_str}\n\n## 릴스 아이디어 20개\n\n")
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
    print(f"  🚀 재테크 릴스+피드 플래너 시작 — {today_str}")
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

    subject   = f"[재테크 콘텐츠] 오늘의 릴스 20 + 피드 20 — {today_str} {theme['name']}"
    html_body = build_email_html(sheet_success, trends, reels, feed)

    try:
        send_gmail(subject, html_body)
    except Exception as e:
        print(f"  ❌ Gmail 발송 실패: {e} → 파일 저장으로 대체")
        save_fallback(reels, feed, today_str)

    print(f"\n{'='*55}")
    print("  ✅ 재테크 릴스+피드 플래너 완료!")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
