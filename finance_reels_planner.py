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
    "/exec"
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
    """Google Sheets Apps Script에서 피드백 데이터 수집."""
    FIN_FILTER = {"재테크", "경제", "투자", "부동산", "주식"}
    patterns: dict[str, list[str]] = {"good": [], "bad": []}
    try:
        resp = requests.get(SHEETS_URL, timeout=10)
        resp.raise_for_status()
        rows = resp.json()
        if not isinstance(rows, list):
            return patterns, False

        for row in rows:
            field = str(row.get("분야", ""))
            if not any(kw in field for kw in FIN_FILTER):
                continue
            result = str(row.get("결과", "")).strip()
            title  = str(row.get("제목", "")).strip()
            if not title:
                continue
            if result in ("good", "성공", "잘됨", "바이럴"):
                patterns["good"].append(title)
            elif result in ("bad", "실패", "저조"):
                patterns["bad"].append(title)

        print(f"  📊 시트 데이터: good={len(patterns['good'])}, bad={len(patterns['bad'])}")
        return patterns, True
    except Exception as e:
        print(f"  시트 수집 실패: {e}")
        return patterns, False


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
# Part 4: 프롬프트 / 이메일 / main()
# ══════════════════════════════════════════

def build_idea_prompt_finance(kw_slot: dict, feedback_examples: str, history_titles: list[str]) -> str:
    root    = kw_slot["root_keyword"]
    sub     = kw_slot["sub_keyword"]
    engine  = kw_slot["engine"]
    persona = kw_slot["persona"]
    tier    = kw_slot["tier"]

    tier_guide = {
        "유입":   "처음 보는 사람도 멈추게. 전문용어 최소화. 저장/팔로우 유도.",
        "전환":   "DM/댓글 CTA 필수. 숫자·비교·체크리스트 형식 선호.",
        "타이밍": '"오늘 이거 나왔어요" 긴박감. 정책 변경일 당일 업로드 가정.',
    }.get(tier, "")

    recent_titles_str = "\n".join(history_titles[:30]) if history_titles else "없음"

    return f"""채널 포지셔닝: "바쁜 직장인도 월급날 30분이면 챙기는 재테크 루틴"
톤: 직장인 공감형 — 데이터 기반, 군더더기 없이, 아래 보지 않음

## 오늘의 키워드 슬롯
- 루트: {root}
- 서브: {sub}  ← 제목 앞 15자 안에 반드시 포함
- 엔진: {engine} — {CONTENT_ENGINES[engine]}
- 페르소나: {PERSONAS[persona]}

## tier 가이드 ({tier})
{tier_guide}

## 최근 생성 제목 (중복 금지)
{recent_titles_str}

## 과거 콘텐츠 피드백
{feedback_examples}

## 출력 형식 (이 형식으로만)
**아이디어 제목:** [제목 — 앞 15자에 서브 키워드 포함]
**릴스 후킹 카피 (첫 3초):** [한 문장, 직장인 공감형]
**릴스 촬영 연출:** [스마트폰만으로 가능한 장면]
**피드 커버 카피:** [숫자 또는 질문으로 시작]
**피드 슬라이드 구성:** [슬라이드 수 + 각 장 핵심 내용]
**CTA:** ["댓글에 'XX' 남겨주시면 자료 보내드립니다" 형식]"""


def build_email_html_finance(
    slots: list[dict],
    ideas: list[dict],
    trends: dict,
    sheet_success: bool,
) -> str:
    TIER_BADGE = {
        "유입":   ('<span style="background:#2563EB;color:#fff;padding:2px 8px;'
                   'border-radius:10px;font-size:11px;font-weight:bold;">🔵 유입</span>'),
        "전환":   ('<span style="background:#16A34A;color:#fff;padding:2px 8px;'
                   'border-radius:10px;font-size:11px;font-weight:bold;">🟢 전환</span>'),
        "타이밍": ('<span style="background:#EA580C;color:#fff;padding:2px 8px;'
                   'border-radius:10px;font-size:11px;font-weight:bold;">🟠 타이밍</span>'),
    }
    ENGINE_BADGE = (
        '<span style="background:#6B7280;color:#fff;padding:2px 6px;'
        'border-radius:8px;font-size:10px;margin-left:4px;">{engine}</span>'
    )

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 트렌드 섹션
    trend_html = ""
    for cat, items in trends.items():
        trend_html += f'<h3 style="color:#374151;margin:12px 0 6px;">{cat}</h3><ul>'
        for it in items[:3]:
            trend_html += f'<li><b>{it["title"]}</b><br><small>{it["snippet"]}</small></li>'
        trend_html += "</ul>"

    # 아이디어 카드
    cards_html = ""
    for idea in ideas:
        slot = idea["slot"]
        tier = slot["tier"]
        engine = slot["engine"]
        tier_b   = TIER_BADGE.get(tier, "")
        engine_b = ENGINE_BADGE.format(engine=engine)
        text_html = idea["text"].replace("\n", "<br>")

        cards_html += f"""
<div style="border:1px solid #E5E7EB;border-radius:10px;padding:16px;margin:12px 0;background:#FAFAFA;">
  <div style="margin-bottom:8px;">{tier_b}{engine_b}</div>
  <div style="font-size:12px;color:#6B7280;margin-bottom:8px;">
    🔑 <b>{slot["root_keyword"]}</b> / {slot["sub_keyword"]}
  </div>
  <div style="font-size:14px;line-height:1.7;">{text_html}</div>
</div>"""

    sheet_status = "✅ 성공" if sheet_success else "❌ 실패"

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:Apple SD Gothic Neo,sans-serif;max-width:700px;margin:auto;padding:20px;color:#111;">

<h1 style="background:linear-gradient(135deg,#1E40AF,#065F46);color:#fff;padding:16px;border-radius:12px;">
  💰 재테크 릴스 플래너 — {now_str}
</h1>

<p style="color:#6B7280;font-size:13px;">
  시트 데이터: {sheet_status} &nbsp;|&nbsp;
  타이밍 키워드: {", ".join(KEYWORD_TIERS["타이밍"]) or "없음"}
</p>

<h2 style="border-bottom:2px solid #1E40AF;padding-bottom:6px;">📡 이번 주 트렌드</h2>
{trend_html}

<h2 style="border-bottom:2px solid #065F46;padding-bottom:6px;margin-top:24px;">
  💡 아이디어 슬롯 {len(ideas)}개
</h2>
{cards_html}

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
    print("=== 재테크 릴스 플래너 시작 ===")

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

    # 4. 월간 업데이트 체크
    this_month = datetime.now().strftime("%Y-%m")
    if history.get("last_tree_update_finance") != this_month:
        print("  🌿 월간 키워드 트리 업데이트 중...")
        history = monthly_keyword_tree_update_finance(history, client)

    # 5. 트렌드 수집 + 타이밍 키워드 추출
    print("  📡 RSS 트렌드 수집 중...")
    trends = search_trends()
    extract_timing_keywords_finance(trends)

    # 6. 시트 데이터 수집 (피드백용)
    print("  📊 시트 데이터 수집 중...")
    patterns, sheet_success = fetch_sheet_data()

    # 7. 주간 키워드 10개 선택
    print("  🔑 키워드 슬롯 선택 중...")
    slots = select_weekly_keywords_finance(history, client)

    # 8. 피드백 예시 + 히스토리 제목
    feedback_parts = []
    if patterns["good"]:
        feedback_parts.append("잘된 제목:\n" + "\n".join(patterns["good"][:5]))
    if patterns["bad"]:
        feedback_parts.append("저조한 제목:\n" + "\n".join(patterns["bad"][:5]))
    feedback_examples = "\n\n".join(feedback_parts) if feedback_parts else "피드백 데이터 없음"

    history_titles: list[str] = []
    for k, v in history.items():
        if len(k) == 10 and k >= "2024-01-01" and isinstance(v, list):
            history_titles.extend(v)

    # 9. 슬롯별 아이디어 생성 (Haiku)
    print("  💡 아이디어 생성 중 (10개)...")
    ideas: list[dict] = []
    for i, slot in enumerate(slots, 1):
        prompt = build_idea_prompt_finance(slot, feedback_examples, history_titles)
        try:
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}],
            )
            idea_text = msg.content[0].text.strip()
            print(f"    [{i}/10] {slot['sub_keyword']} ✓")
        except Exception as e:
            idea_text = f"생성 실패: {e}"
            print(f"    [{i}/10] {slot['sub_keyword']} ✗ {e}")
        ideas.append({"slot": slot, "text": idea_text})

        # 히스토리 제목 추적 (중복 방지용)
        first_line = idea_text.split("\n")[0].replace("**아이디어 제목:**", "").strip()
        today = datetime.now().strftime("%Y-%m-%d")
        history.setdefault(today, []).append(first_line)

    # 10. history 저장
    history["keyword_tree_finance"] = {
        k: {
            "modifiers": v["modifiers"],
            "angles":    v["angles"],
            "used_subs": v["used_subs"],
        }
        for k, v in KEYWORD_TREE.items()
    }
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    print(f"  💾 history 저장 완료: {HISTORY_FILE}")

    # 11. 이메일 발송
    now_str = datetime.now().strftime("%Y-%m-%d")
    subject = f"[재테크 릴스] 주간 아이디어 {len(ideas)}개 — {now_str}"
    html = build_email_html_finance(slots, ideas, trends, sheet_success)
    send_gmail(subject, html)

    print("=== 완료 ===")


if __name__ == "__main__":
    main()
