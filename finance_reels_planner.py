"""
재테크 콘텐츠 플래너 v2 — KEYWORD_TREE 기반 키워드 전략
===========================================================
STEP 1. history.json 로드 + 월간 키워드 트리 업데이트 체크
STEP 2. RSS 트렌드 수집 + 타이밍 키워드 추출
STEP 3. 주간 키워드 10개 선택 (유입2 : 전환6 : 타이밍2)
STEP 4. 키워드별 아이디어 생성 (Claude Haiku)
STEP 5. Gmail HTML 이메일 발송 (tier/engine 배지 포함)
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

GMAIL_ADDRESS     = os.environ.get("GMAIL_ADDRESS",  "lyj990701@gmail.com")
GMAIL_PASSWORD    = os.environ.get("GMAIL_PASSWORD", "ugfj tqjf xecw wvkv")
TO_ADDRESS        = os.environ.get("TO_ADDRESS",     "lyj990701@gmail.com")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

SHEETS_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbxFx0hkilEV-wLasfiIyv_Zchzi7PQWa8_qvdDpg_hsc98v_QKK3CsiwT1mW9I_hewg"
    "/exec?action=readSheet&sheet=Posts"
)

OUTPUT_DIR   = os.path.expanduser("~/reels_outputs")
HISTORY_FILE = os.path.join(OUTPUT_DIR, "finance_history.json")

# ══════════════════════════════════════════
# 전략 상수
# ══════════════════════════════════════════

PERSONAS = {
    "A": "월급 받아도 남는 게 없어서 재테크 시작하고 싶은 직장인",
    "B": "청약·ISA·IRP 있는 건 아는데 제대로 활용 못 하는 사람",
    "C": "포트폴리오 만들고 경제적 자유 로드맵 짜고 싶은 사람",
}

CONTENT_ENGINES = {
    "정책·혜택 해석":      "정부 정책·혜택 변경을 직장인 기준으로 해석. 변경 당일 업로드.",
    "돈 안 모이는 이유→해결": "직장인 공통 실패 경험 + 해결법. 공감 먼저, 솔루션 나중.",
    "상품·방법 비교":      "같은 조건 다른 선택지 비교. 숫자 기반 신뢰형.",
    "루틴·포트폴리오 공개": "실제 운영 루틴·수익률 공개. 내 성장이 시리즈.",
}

KEYWORD_TREE = {
    "직장인 재테크": {
        "tier": "유입",
        "engine_fit": ["정책·혜택 해석", "루틴·포트폴리오 공개"],
        "modifiers": ["20대", "30대", "맞벌이", "사회초년생", "월급 200", "월급 300",
                      "ISA", "IRP", "청약", "ETF", "연금"],
        "angles":    ["시작법", "루틴", "현실", "로드맵", "실수", "체크리스트", "공개"],
        "used_subs": [],
    },
    "월급 관리": {
        "tier": "전환",
        "engine_fit": ["돈 안 모이는 이유→해결", "루틴·포트폴리오 공개"],
        "modifiers": ["통장 쪼개기", "자동이체", "비상금", "고정비", "변동비",
                      "소비 패턴", "저축률", "식비", "구독 정리"],
        "angles":    ["방법", "실패 이유", "루틴 공개", "바꾼 것", "얼마씩", "결과"],
        "used_subs": [],
    },
    "돈 모으는 법": {
        "tier": "유입",
        "engine_fit": ["돈 안 모이는 이유→해결", "상품·방법 비교"],
        "modifiers": ["직장인", "20대", "30대", "월급 200", "월급 300", "맞벌이",
                      "1년 만에", "종잣돈", "1000만원"],
        "angles":    ["현실", "루틴", "비결", "실패 이유", "처음", "빠르게"],
        "used_subs": [],
    },
    "재테크 공부": {
        "tier": "전환",
        "engine_fit": ["상품·방법 비교", "정책·혜택 해석"],
        "modifiers": ["ETF", "주식", "부동산", "절세", "청약", "배당",
                      "ISA", "IRP", "연금저축", "금리"],
        "angles":    ["처음 하는 법", "추천", "순서", "실수", "정리", "비교"],
        "used_subs": [],
    },
}

KEYWORD_TIERS = {
    "유입":   [k for k, v in KEYWORD_TREE.items() if v["tier"] == "유입"],
    "전환":   [k for k, v in KEYWORD_TREE.items() if v["tier"] == "전환"],
    "타이밍": [],  # 트렌드 수집 후 동적으로 채움
}

POLICY_KEYWORDS = [
    "청약", "ISA", "IRP", "연금저축", "금리", "기준금리",
    "부동산", "취득세", "종부세", "연말정산", "퇴직연금",
]

# 시트 접근 실패 시 폴백 패턴
FALLBACK_PATTERNS = {
    "thumbnail": [
        "직장인 ISA 이렇게 쓰면 세금 0원 → 숫자형",
        "월급 300인데 저축 0원인 이유 5가지 → 실패 이유형",
        "IRP 모르면 퇴직금 30% 날립니다 → 모르면 손해형",
        "30대 재테크 루틴 공개합니다 → 공개형",
        "청약 vs ISA vs IRP 뭐부터? → 비교형",
        "재테크 처음이라면 이 순서대로 → 순서형",
    ],
    "hook_3sec": [
        "월급날만 기다리는데 왜 통장에 돈이 없을까요?",
        "이거 모르면 세금만 더 내는 거예요.",
        "재테크 시작하려는데 뭐부터 해야 할지 모르죠?",
        "직장인 재테크 딱 이 순서대로만 하세요.",
    ],
    "hook_copy": [
        "댓글에 '재테크' 남겨주시면 자료 보내드립니다!",
        "저장해두고 월급날 꺼내보세요 📌",
        "팔로우하면 매주 재테크 꿀팁 드려요",
    ],
    "caption": [
        "오프닝: 직장인 공감 문장 (월급 받아도 남는 게 없죠?)",
        "본문: 핵심 정보 2-3줄, 숫자 포함",
        "CTA: 댓글에 키워드 남기면 자료 DM",
    ],
}

# RSS 소스
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

# ══════════════════════════════════════════
# Part 2: RSS / 시트 / 트렌드 함수
# ══════════════════════════════════════════

def _fetch_rss(url: str, max_items: int = 4) -> list[dict]:
    """RSS URL에서 title/snippet 목록 반환."""
    try:
        resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = []
        # RSS 2.0
        for item in root.iter("item"):
            title_el   = item.find("title")
            snippet_el = item.find("description")
            title   = title_el.text.strip()   if title_el   and title_el.text   else ""
            snippet = snippet_el.text.strip() if snippet_el and snippet_el.text else ""
            if title:
                items.append({"title": title, "snippet": snippet[:120]})
            if len(items) >= max_items:
                break
        # Atom
        if not items:
            for entry in root.findall("atom:entry", ns):
                title_el   = entry.find("atom:title",   ns)
                snippet_el = entry.find("atom:summary", ns)
                title   = title_el.text.strip()   if title_el   and title_el.text   else ""
                snippet = snippet_el.text.strip() if snippet_el and snippet_el.text else ""
                if title:
                    items.append({"title": title, "snippet": snippet[:120]})
                if len(items) >= max_items:
                    break
        return items
    except Exception as e:
        print(f"  RSS 오류 {url}: {e}")
        return []


def search_trends() -> dict:
    """RSS 수집 → 카테고리별 트렌드 dict 반환."""
    trends: dict[str, list[dict]] = {}
    for category, urls in _FIN_RSS_SOURCES.items():
        items: list[dict] = []
        for url in urls:
            items.extend(_fetch_rss(url, max_items=4))
            if len(items) >= 6:
                break
        trends[category] = items[:6]
        print(f"  📡 {category}: {len(trends[category])}건")

    # 폴백: 빈 카테고리 채우기
    for cat, items in trends.items():
        if not items:
            trends[cat] = [{"title": f"{cat} 트렌드 수집 실패", "snippet": "RSS 오류"}]

    return trends


def fetch_sheet_data() -> tuple[dict, bool]:
    """Google Sheets에서 분야(C열) 재테크 관련 행만 필터링해 패턴 수집."""
    FIN_FILTER = {"재테크", "경제", "투자", "부동산", "주식"}
    try:
        resp = requests.get(SHEETS_URL, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])

        # 분야(C열)에 재테크 관련 키워드 포함된 행만 필터
        filtered = [
            r for r in results
            if any(kw in str(r.get("분야", "")) for kw in FIN_FILTER)
        ]
        print(f"  → 전체 {len(results)}행 중 재테크 {len(filtered)}행 필터링")

        patterns = {
            "thumbnail": [r.get("썸네일 문구", "") for r in filtered if r.get("썸네일 문구")],
            "hook_3sec": [r.get("첫 3초 훅",   "") for r in filtered if r.get("첫 3초 훅")],
            "hook_copy": [r.get("후킹 멘트",   "") for r in filtered if r.get("후킹 멘트")],
            "caption":   [r.get("캡션",        "") for r in filtered if r.get("캡션")],
            "good":      [r.get("좋은점",      "") for r in filtered if r.get("좋은점")],
            "bad":       [r.get("아쉬운점",    "") for r in filtered if r.get("아쉬운점")],
        }
        print("  ✅ 실시간 시트 데이터 반영 완료")
        return patterns, True

    except Exception as e:
        print(f"  ⚠️  시트 접근 실패 ({e}) → 폴백 데이터 사용")
        return FALLBACK_PATTERNS, False


# ══════════════════════════════════════════
# Part 3: 키워드 트리 함수
# ══════════════════════════════════════════

def extract_timing_keywords_finance(trends: dict) -> None:
    """트렌드 title/snippet에서 POLICY_KEYWORDS 감지 → KEYWORD_TIERS["타이밍"] 갱신."""
    found: list[str] = []
    for items in trends.values():
        for item in items:
            text = item.get("title", "") + " " + item.get("snippet", "")
            for kw in POLICY_KEYWORDS:
                if kw in text and kw not in found:
                    found.append(kw)
    KEYWORD_TIERS["타이밍"] = found[:4]
    print(f"  🕐 타이밍 키워드: {KEYWORD_TIERS['타이밍']}")


def get_sub_keyword_finance(root_key: str, client) -> str:
    """modifier × angle 조합 생성 → Haiku로 자연스러운 검색어로 다듬어 반환."""
    entry = KEYWORD_TREE[root_key]
    modifiers  = entry["modifiers"]
    angles     = entry["angles"]
    used_subs  = entry["used_subs"]

    # 모든 조합 생성
    combos = [f"{m} {a}" for m in modifiers for a in angles]
    unused = [c for c in combos if c not in used_subs]
    if not unused:
        entry["used_subs"] = []
        unused = combos

    raw_combo = unused[0]

    # Haiku로 자연스러운 검색어로 다듬기
    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=60,
            messages=[{
                "role": "user",
                "content": (
                    f"다음 재테크 키워드 조합을 인스타그램 검색어로 자연스럽게 다듬어줘.\n"
                    f"조합: {root_key} {raw_combo}\n"
                    f"조건: 15자 이내, 한국어, 검색어 하나만 출력 (설명 없이)"
                ),
            }],
        )
        refined = msg.content[0].text.strip().strip('"').strip("'")
        if len(refined) > 20 or "\n" in refined:
            refined = f"{root_key} {raw_combo}"[:20]
    except Exception:
        refined = f"{root_key} {raw_combo}"[:20]

    entry["used_subs"].append(raw_combo)
    return refined


def load_keyword_tree_from_history_finance(history: dict) -> None:
    """history["keyword_tree_finance"]에서 KEYWORD_TREE 상태 복원."""
    saved = history.get("keyword_tree_finance", {})
    if not isinstance(saved, dict):
        return
    for root_key, saved_entry in saved.items():
        if root_key in KEYWORD_TREE and isinstance(saved_entry, dict):
            for field in ("modifiers", "angles", "used_subs"):
                if field in saved_entry and isinstance(saved_entry[field], list):
                    KEYWORD_TREE[root_key][field] = saved_entry[field]


def select_weekly_keywords_finance(history: dict, client) -> list[dict]:
    """유입 2 : 전환 6 : 타이밍 2 = 10개 키워드 슬롯 선택."""
    slots: list[dict] = []
    used_recent: list[str] = history.get("keywords_used_finance", [])[-40:]

    tier_plan = [("유입", 2), ("전환", 6), ("타이밍", 2)]

    for tier, count in tier_plan:
        pool = list(KEYWORD_TIERS[tier])

        # 타이밍 키워드 없으면 유입에서 보충
        if not pool:
            pool = list(KEYWORD_TIERS["유입"])
            tier = "유입"

        # used_recent 제외된 것 우선, 없으면 전체 pool
        fresh = [k for k in pool if k not in [u.split("|")[0] for u in used_recent]]
        pick_pool = fresh if fresh else pool

        for i in range(count):
            root = pick_pool[i % len(pick_pool)]

            # KEYWORD_TREE에 없는 타이밍 키워드 처리 (동적으로 생성된 키워드)
            if root not in KEYWORD_TREE:
                sub_kw = root
            else:
                sub_kw = get_sub_keyword_finance(root, client)

            # engine_fit 순환 선택
            if root in KEYWORD_TREE:
                engine_fits = KEYWORD_TREE[root]["engine_fit"]
                engine = engine_fits[i % len(engine_fits)]
            else:
                engine = list(CONTENT_ENGINES.keys())[0]

            # tier별 페르소나
            persona = "A" if tier == "유입" else "B"

            slots.append({
                "root_keyword": root,
                "sub_keyword":  sub_kw,
                "tier":         tier,
                "engine":       engine,
                "persona":      persona,
            })
            history.setdefault("keywords_used_finance", []).append(f"{root}|{sub_kw}")

    print(f"  🔑 슬롯 선택: 유입×2, 전환×6, 타이밍×2 → 총 {len(slots)}개")
    return slots


def monthly_keyword_tree_update_finance(history: dict, client) -> dict:
    """시트 데이터 기반으로 KEYWORD_TREE modifier/angle 월간 업데이트."""
    try:
        resp = requests.get(SHEETS_URL, timeout=10)
        resp.raise_for_status()
        rows = resp.json() if isinstance(resp.json(), list) else []
    except Exception as e:
        print(f"  월간 업데이트 시트 수집 실패: {e}")
        rows = []

    # 지난달 날짜 + 재테크/경제/투자 필터
    last_month = (datetime.now().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    FIN_FILTER = {"재테크", "경제", "투자", "부동산", "주식"}
    recent_titles = [
        str(row.get("제목", ""))
        for row in rows
        if str(row.get("시간", "")).startswith(last_month)
        and any(kw in str(row.get("분야", "")) for kw in FIN_FILTER)
    ]

    context = "\n".join(recent_titles[:20]) if recent_titles else "데이터 없음"

    for root_key in KEYWORD_TREE:
        prompt = (
            f"재테크 인스타그램 채널의 지난달 콘텐츠:\n{context}\n\n"
            f"루트 키워드 '{root_key}'에 맞는 새로운 수식어(modifiers) 3개와 "
            f"각도(angles) 3개를 JSON으로만 출력해줘.\n"
            f"형식: {{\"modifiers\": [\"...\", \"...\", \"...\"], \"angles\": [\"...\", \"...\", \"...\"]}}"
        )
        try:
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.content[0].text.strip()
            # regex로 JSON 추출
            m = re.search(r'\{[^{}]*"modifiers"[^{}]*\}', raw, re.DOTALL)
            if m:
                data = json.loads(m.group())
                new_mods   = [str(x) for x in data.get("modifiers", [])[:3]]
                new_angles = [str(x) for x in data.get("angles",    [])[:3]]
                if new_mods:
                    KEYWORD_TREE[root_key]["modifiers"].extend(new_mods)
                if new_angles:
                    KEYWORD_TREE[root_key]["angles"].extend(new_angles)
                print(f"  🌿 {root_key}: +{len(new_mods)} modifiers, +{len(new_angles)} angles")
        except Exception as e:
            print(f"  월간 업데이트 {root_key} 실패: {e}")

    history["last_tree_update_finance"] = datetime.now().strftime("%Y-%m")
    history["keyword_tree_finance"] = {
        k: {
            "modifiers": v["modifiers"],
            "angles":    v["angles"],
            "used_subs": v["used_subs"],
        }
        for k, v in KEYWORD_TREE.items()
    }
    return history


# ══════════════════════════════════════════
# Part 4: 히스토리 / 폴백 유틸
# ══════════════════════════════════════════

def load_recent_titles(days: int = 21) -> list[str]:
    """최근 N일 치 아이디어 제목 로드 (중복 방지용)."""
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, encoding="utf-8") as f:
            history = json.load(f)
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        recent = []
        for date, titles in history.items():
            if len(date) == 10 and date >= cutoff and isinstance(titles, list):
                recent.extend(titles)
        return recent
    except Exception:
        return []


def save_titles_to_history(reels_output: str, feed_output: str = "") -> None:
    """생성된 아이디어 제목을 history 파일에 저장."""
    today = datetime.now().strftime("%Y-%m-%d")
    titles = re.findall(r"\*\*아이디어 제목:\*\*\s*(.+)", reels_output + feed_output)
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
    cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    history = {k: v for k, v in history.items() if k >= cutoff or not (len(k) == 10)}
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    print(f"  📝 히스토리 저장: {len(titles)}개 제목 → {HISTORY_FILE}")


def save_fallback_finance(reels_output: str, feed_output: str, today_str: str) -> None:
    """이메일 발송 실패 시 파일로 저장."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, f"reels-finance-{today_str}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# 재테크 릴스 — {today_str}\n\n## 릴스 아이디어 10개\n\n")
        f.write(reels_output)
        f.write("\n\n## 피드(카드뉴스) 아이디어 10개\n\n")
        f.write(feed_output)
    print(f"  💾 폴백 저장 완료: {path}")


# ══════════════════════════════════════════
# Part 5: 프롬프트 / 이메일 / main()
# ══════════════════════════════════════════

def build_reels_prompt_finance(
    slots: list[dict],
    patterns: dict,
    trends: dict,
    recent_titles: list[str],
) -> str:
    today = datetime.now().strftime("%Y년 %m월 %d일")
    week_num = datetime.now().isocalendar()[1]

    thumbnails = patterns.get("thumbnail", FALLBACK_PATTERNS["thumbnail"])[:6]
    hooks_3sec = patterns.get("hook_3sec", FALLBACK_PATTERNS["hook_3sec"])[:4]
    hooks_copy = patterns.get("hook_copy", FALLBACK_PATTERNS["hook_copy"])[:4]
    captions   = patterns.get("caption",   FALLBACK_PATTERNS["caption"])[:3]
    goods      = patterns.get("good",  [])[:6]
    bads       = patterns.get("bad",   [])[:6]

    trend_lines = []
    for cat, items in trends.items():
        trend_lines.append(f"\n**{cat}:**")
        for item in items[:3]:
            trend_lines.append(f"  - {item['title']}: {item.get('snippet','')[:100]}")

    avoid_block = (
        "\n".join(f"- {t}" for t in recent_titles[:40])
        if recent_titles else "- (첫 실행 — 제한 없음)"
    )

    feedback_block = ""
    if goods or bads:
        feedback_block = "\n## 과거 콘텐츠 피드백 (시트 기반)\n"
        if goods:
            feedback_block += "**잘 된 점:**\n" + "\n".join(f"- {g}" for g in goods) + "\n"
        if bads:
            feedback_block += "**아쉬운 점 (반복 금지):**\n" + "\n".join(f"- {b}" for b in bads) + "\n"

    # 슬롯 테이블
    slot_lines = []
    for i, s in enumerate(slots, 1):
        tier_guide = {
            "유입":   "저장/팔로우 유도. 전문용어 최소화.",
            "전환":   "DM/댓글 CTA 필수. 숫자·비교·체크리스트 선호.",
            "타이밍": '"오늘 이거 나왔어요" 긴박감.',
        }.get(s["tier"], "")
        slot_lines.append(
            f"#{i} | 루트: {s['root_keyword']} | 서브: {s['sub_keyword']} | "
            f"tier: {s['tier']} ({tier_guide}) | 엔진: {s['engine']} | 페르소나: {PERSONAS[s['persona']]}"
        )
    slots_block = "\n".join(slot_lines)

    return f"""당신은 재테크 인스타그램 채널 콘텐츠 디렉터입니다.
오늘({today}, {week_num}주차) 아래 10개 슬롯에 맞춰 릴스 + 피드 아이디어를 각 1개씩 생성하세요.

## 채널 포지셔닝
"바쁜 직장인도 월급날 30분이면 챙기는 재테크 루틴"
톤: 직장인 공감형 — 데이터 기반, 군더더기 없이

## 10개 슬롯 (순서대로 생성)
{slots_block}

## 최근 21일 다룬 주제 (반드시 피하거나 완전히 다른 각도로)
{avoid_block}
{feedback_block}
## 실제 시트 패턴 (이 톤·구조·길이를 최대한 따를 것)
**썸네일 문구 패턴:**
{chr(10).join(f"- {t}" for t in thumbnails)}

**첫 3초 훅 패턴:**
{chr(10).join(f"- {h}" for h in hooks_3sec)}

**후킹 멘트:**
{chr(10).join(f"- {h}" for h in hooks_copy)}

**캡션 구조:**
{chr(10).join(f"- {c}" for c in captions)}

## 오늘의 트렌드
{"".join(trend_lines)}

## 출력 형식 (정확히 이 형식, 10개 모두)

---

**아이디어 #N**

**아이디어 제목:** [제목 — 서브 키워드를 앞 15자 안에 반드시 포함]
**릴스 후킹 카피 (첫 3초):** [스크롤 멈추게 하는 한 문장, 직장인 공감형]
**릴스 촬영 연출:** [스마트폰만으로 가능한 구체적 장면]
**피드 커버 카피:** [숫자 또는 질문으로 시작]
**피드 슬라이드 구성:** [슬라이드 수 + 각 장 핵심 내용]
**CTA:** ["댓글에 'XX' 남겨주시면 자료 보내드립니다" 형식]

---

**중요 원칙:**
- 썸네일: 숫자형 / 질문형 / 비교형 / "모르면 손해"형 골고루
- 모든 아이디어는 스마트폰만으로 즉시 촬영 가능해야 함
- tier별 가이드 반드시 반영할 것"""


def generate_reels_finance(
    slots: list[dict],
    patterns: dict,
    trends: dict,
    client,
    recent_titles: list[str],
) -> str:
    print("\n🤖 [STEP 4] 재테크 릴스 아이디어 10개 생성 중... (Haiku 스트리밍)")
    prompt = build_reels_prompt_finance(slots, patterns, trends, recent_titles)

    text = ""
    with client.messages.stream(
        model="claude-haiku-4-5-20251001",
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for chunk in stream.text_stream:
            text += chunk
            print(chunk, end="", flush=True)

    print("\n  ✅ 릴스 아이디어 생성 완료")
    return text


def build_feed_prompt_finance(
    slots: list[dict],
    patterns: dict,
    trends: dict,
    recent_titles: list[str],
) -> str:
    today = datetime.now().strftime("%Y년 %m월 %d일")
    week_num = datetime.now().isocalendar()[1]

    thumbnails = patterns.get("thumbnail", FALLBACK_PATTERNS["thumbnail"])[:6]
    goods      = patterns.get("good",  [])[:6]
    bads       = patterns.get("bad",   [])[:6]

    trend_lines = []
    for cat, items in trends.items():
        trend_lines.append(f"\n**{cat}:**")
        for item in items[:3]:
            trend_lines.append(f"  - {item['title']}: {item.get('snippet','')[:100]}")

    avoid_block = (
        "\n".join(f"- {t}" for t in recent_titles[:40])
        if recent_titles else "- (첫 실행 — 제한 없음)"
    )

    feedback_block = ""
    if goods or bads:
        feedback_block = "\n## 과거 콘텐츠 피드백\n"
        if goods:
            feedback_block += "**잘 된 점:**\n" + "\n".join(f"- {g}" for g in goods) + "\n"
        if bads:
            feedback_block += "**아쉬운 점 (반복 금지):**\n" + "\n".join(f"- {b}" for b in bads) + "\n"

    slot_lines = []
    for i, s in enumerate(slots, 1):
        slot_lines.append(
            f"#{i} | 루트: {s['root_keyword']} | 서브: {s['sub_keyword']} | tier: {s['tier']} | 엔진: {s['engine']}"
        )

    return f"""당신은 재테크 인스타그램 채널 콘텐츠 디렉터입니다.
오늘({today}, {week_num}주차) 아래 10개 슬롯에 맞춰 피드(카드뉴스/캐러셀) 아이디어를 각 1개씩 생성하세요.

## 채널 포지셔닝
"바쁜 직장인도 월급날 30분이면 챙기는 재테크 루틴"
저장율 높이는 체크리스트·비교표·단계별 가이드 형식 선호

## 10개 슬롯
{chr(10).join(slot_lines)}

## 최근 21일 다룬 주제 (반드시 피하거나 완전히 다른 각도로)
{avoid_block}
{feedback_block}
## 썸네일 패턴
{chr(10).join(f"- {t}" for t in thumbnails)}

## 오늘의 트렌드
{"".join(trend_lines)}

## 출력 형식 (정확히 이 형식, 10개 모두)

---

**피드 아이디어 #N**

**아이디어 제목:** [제목 — 서브 키워드를 앞 15자 안에 반드시 포함]
**카드 구성:** [슬라이드 수 — 최대 10장]
**커버 카드 카피:** [숫자 또는 질문으로 시작]
**슬라이드별 내용:**
  - 1장: [커버 훅]
  - 2장: [핵심 내용 1]
  - 3장: [핵심 내용 2]
  - 마지막 장: [정리 + CTA]
**디자인 방향:** [배경색 톤, 핵심 시각 요소 — 1줄]
**캡션 첫 줄:** [검색 유입 + 저장 유도. 댓글 키워드 CTA 적용]

---

**중요 원칙:**
- 커버는 숫자 또는 질문으로 반드시 시작
- 댓글 CTA: "댓글에 'XX' 남겨주시면 자료 보내드립니다" 패턴 10개 중 최소 4개 적용
- 모든 아이디어는 스마트폰 + Canva 무료 버전으로 제작 가능해야 함"""


def generate_feed_finance(
    slots: list[dict],
    patterns: dict,
    trends: dict,
    client,
    recent_titles: list[str],
) -> str:
    print("\n🤖 [STEP 5] 재테크 피드 아이디어 10개 생성 중... (Haiku 스트리밍)")
    prompt = build_feed_prompt_finance(slots, patterns, trends, recent_titles)

    text = ""
    with client.messages.stream(
        model="claude-haiku-4-5-20251001",
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for chunk in stream.text_stream:
            text += chunk
            print(chunk, end="", flush=True)

    print("\n  ✅ 피드 아이디어 생성 완료")
    return text


def build_trend_html(trends: dict) -> str:
    html = ""
    for cat, items in trends.items():
        html += f'<h3 style="color:#1E40AF;margin:16px 0 8px;font-size:15px;">{cat}</h3>'
        html += '<ul style="margin:0 0 8px;padding-left:20px;">'
        for item in items[:3]:
            title   = item.get("title", "")
            snippet = item.get("snippet", "")[:150]
            url     = item.get("url", "")
            link    = (f'<a href="{url}" style="color:#1a1a1a;font-weight:bold;">{title}</a>'
                       if url else f"<strong>{title}</strong>")
            html += f'<li style="margin-bottom:8px;">{link}<br><span style="color:#666;font-size:12px;">{snippet}</span></li>'
        html += "</ul>"
    return html


def content_to_html(raw: str) -> str:
    html = raw
    html = re.sub(r"\n---\n", '\n<hr style="border:none;border-top:1px solid #EBEBEB;margin:24px 0;">\n', html)
    html = re.sub(
        r"\*\*(아이디어 #\d+)\*\*",
        r'<h3 style="color:#1a1a1a;font-size:16px;margin:20px 0 12px;">💰 \1</h3>',
        html,
    )
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = html.replace("\n", "<br>")
    return html


def build_slot_badges(slots: list[dict]) -> str:
    """슬롯별 tier/engine 배지 헤더 HTML 생성."""
    TIER_BADGE = {
        "유입":   '<span style="background:#2563EB;color:#fff;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:bold;">🔵 유입</span>',
        "전환":   '<span style="background:#16A34A;color:#fff;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:bold;">🟢 전환</span>',
        "타이밍": '<span style="background:#EA580C;color:#fff;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:bold;">🟠 타이밍</span>',
    }
    ENGINE_TPL = '<span style="background:#6B7280;color:#fff;padding:2px 6px;border-radius:8px;font-size:10px;margin-left:4px;">{e}</span>'
    rows = []
    for i, s in enumerate(slots, 1):
        tier_b   = TIER_BADGE.get(s["tier"], "")
        engine_b = ENGINE_TPL.format(e=s["engine"])
        kw_b     = f'<span style="font-size:11px;color:#6B7280;margin-left:6px;">#{i} {s["root_keyword"]} / {s["sub_keyword"]}</span>'
        rows.append(f'<div style="margin:4px 0;">{tier_b}{engine_b}{kw_b}</div>')
    return "\n".join(rows)


def build_email_html_finance(
    slots: list[dict],
    reels_output: str,
    feed_output: str,
    trends: dict,
    sheet_success: bool,
) -> str:
    today_kr    = datetime.now().strftime("%Y년 %m월 %d일")
    now_str     = datetime.now().strftime("%Y년 %m월 %d일 %H:%M")
    data_status = "✅ 실시간 시트 데이터 반영" if sheet_success else "⚠️ 폴백 데이터 사용"
    timing_kws  = ", ".join(KEYWORD_TIERS["타이밍"]) or "없음"

    return f"""<!DOCTYPE html>
<html><body style="font-family:'Apple SD Gothic Neo',Arial,sans-serif;max-width:760px;margin:auto;padding:24px;color:#1a1a1a;background:#fff;">

  <h2 style="color:#2D2D2D;border-bottom:3px solid #1E40AF;padding-bottom:10px;margin-bottom:20px;">
    💰 재테크 — 릴스 10 + 피드 10 — {today_kr}
  </h2>

  <div style="background:#F0F7FF;border-left:4px solid #1E40AF;padding:10px 16px;margin-bottom:20px;border-radius:4px;">
    <p style="margin:0;font-size:14px;"><strong>데이터 상태:</strong> {data_status}</p>
    <p style="margin:4px 0 0;font-size:13px;color:#555;"><strong>타이밍 키워드:</strong> {timing_kws}</p>
  </div>

  <div style="background:#F9FFF9;border:1px solid #D1FAE5;padding:12px 16px;margin-bottom:24px;border-radius:8px;">
    <p style="margin:0 0 8px;font-size:13px;font-weight:bold;color:#065F46;">📋 슬롯 구성 (유입 2 : 전환 6 : 타이밍 2)</p>
    {build_slot_badges(slots)}
  </div>

  <h2 style="color:#2D2D2D;font-size:18px;border-bottom:2px solid #EBEBEB;padding-bottom:8px;margin-bottom:16px;">
    📈 이번 주 트렌드
  </h2>
  <div style="margin-bottom:36px;">{build_trend_html(trends)}</div>

  <h2 style="color:#2D2D2D;font-size:18px;border-bottom:2px solid #1E40AF;padding-bottom:8px;margin-bottom:16px;">
    🎬 릴스 아이디어 10개
  </h2>
  <div style="line-height:1.8;font-size:14px;margin-bottom:48px;">
    {content_to_html(reels_output)}
  </div>

  <h2 style="color:#2D2D2D;font-size:18px;border-bottom:2px solid #1E40AF;padding-bottom:8px;margin-bottom:16px;">
    🗂️ 피드(카드뉴스) 아이디어 10개
  </h2>
  <div style="line-height:1.8;font-size:14px;margin-bottom:48px;">
    {content_to_html(feed_output)}
  </div>

  <p style="color:#bbb;font-size:11px;margin-top:40px;text-align:right;">
    자동 생성 — {now_str} | finance_reels_planner.py
  </p>

</body></html>"""


def send_gmail(subject: str, html_body: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_ADDRESS
    msg["To"]      = TO_ADDRESS
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, TO_ADDRESS, msg.as_string())
        print(f"  ✉️ 이메일 발송 완료 → {TO_ADDRESS}")
    except Exception as e:
        print(f"  이메일 발송 실패: {e}")


def main() -> None:
    today_str  = datetime.now().strftime("%Y-%m-%d")
    now        = datetime.now()
    this_month = now.strftime("%Y-%m")
    week_num   = now.isocalendar()[1]

    print(f"\n{'='*55}")
    print(f"  💰 재테크 릴스 플래너 시작 — {today_str} (#{week_num}주차)")
    print(f"{'='*55}\n")

    if not ANTHROPIC_API_KEY:
        raise EnvironmentError("ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다.")

    # 1. history 로드
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    history: dict = {}
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = {}

    # 2. 키워드 트리 복원
    load_keyword_tree_from_history_finance(history)

    # 3. Claude 클라이언트
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # 4. 월간 키워드 트리 업데이트 (이번 달 아직 안 했으면)
    if history.get("last_tree_update_finance") != this_month:
        print("🌿 [STEP 1] 월간 키워드 트리 업데이트 중...")
        history = monthly_keyword_tree_update_finance(history, client)
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)

    # 5. 트렌드 수집 + 타이밍 키워드 추출
    print("\n📡 [STEP 2] RSS 트렌드 수집 중...")
    trends = search_trends()
    extract_timing_keywords_finance(trends)

    # 6. 시트 데이터 수집
    print("\n📊 [STEP 3] Google Sheets 데이터 수집 중...")
    patterns, sheet_success = fetch_sheet_data()

    # 7. 주간 키워드 10개 선택
    print("\n🔑 [STEP 4] 키워드 슬롯 선택 중...")
    slots = select_weekly_keywords_finance(history, client)

    # 8. 최근 제목 로드 (중복 방지)
    recent_titles = load_recent_titles()
    if recent_titles:
        print(f"  🚫 최근 21일 회피 목록: {len(recent_titles)}개 제목 로드")

    # 9. 릴스 10개 생성 (Haiku 스트리밍)
    reels = generate_reels_finance(slots, patterns, trends, client, recent_titles)

    # 10. 피드 10개 생성 (Haiku 스트리밍)
    feed = generate_feed_finance(slots, patterns, trends, client, recent_titles)

    # 11. 히스토리 저장 (제목 + 키워드 트리 상태)
    save_titles_to_history(reels, feed)
    history["keyword_tree_finance"] = {
        k: {"modifiers": v["modifiers"], "angles": v["angles"], "used_subs": v["used_subs"]}
        for k, v in KEYWORD_TREE.items()
    }
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    print(f"  💾 history 저장 완료: {HISTORY_FILE}")

    # 12. 이메일 발송 (실패 시 파일 저장)
    subject   = f"[재테크 릴스] 릴스 10 + 피드 10 — {today_str}"
    html_body = build_email_html_finance(slots, reels, feed, trends, sheet_success)
    try:
        send_gmail(subject, html_body)
    except Exception as e:
        print(f"  ❌ Gmail 발송 실패: {e} → 파일 저장으로 대체")
        save_fallback_finance(reels, feed, today_str)

    print(f"\n{'='*55}")
    print("  ✅ 재테크 릴스 플래너 완료!")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
