"""
재테크 릴스 플래너 — 매일 오전 9시 자동 실행
=====================================================
STEP 1. Google Sheets (Apps Script)에서 기존 재테크 콘텐츠 패턴 수집
STEP 2. 오늘의 재테크/경제/투자 트렌드 웹 서치
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
        "월급쟁이도 할 수 있는 ETF 투자법 5가지 → 즉시활용 + 숫자형",
        "이거 모르면 돈 새고 있는 거예요... → 모르면 손해형",
        "재테크 1년 했더니 생긴 일 → 공감 + 스토리형",
        "직장인 평균 저축률 vs 내 저축률 비교해봤어요 → 비교/충격형",
        "통장 쪼개기, 이렇게 하면 됩니다 → 내부자팁형",
        "요즘 MZ가 많이 한다는 재테크 방법 → 트렌드형",
    ],
    "caption": [
        "오프닝: 공감/감탄 문장 (월급날만 기다리고 계신가요?, 저도 처음엔 몰랐어요...)",
        "본문: 핵심 팁 1-2줄, 구체적인 숫자 포함",
        "CTA: 댓글에 'OO' 남겨주시면 자료 보내드립니다!, 저장해두고 나중에 써보세요!",
    ],
}


# ══════════════════════════════════════════
# STEP 1 — Google Sheets 데이터 수집
# ══════════════════════════════════════════

def fetch_sheet_data():
    """Google Apps Script URL에서 시트 데이터 가져와 재테크 행만 필터링"""
    print("📊 [STEP 1] Google Sheets 데이터 수집 중...")
    try:
        resp = requests.get(SHEETS_URL, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])

        # 재테크 관련 행만 필터링
        filtered = [
            r for r in results
            if "재테크" in str(r.get("분야", "")) or "경제" in str(r.get("분야", "")) or "투자" in str(r.get("분야", ""))
        ]
        print(f"  → 전체 {len(results)}행 중 재테크/경제/투자 {len(filtered)}행 필터링")

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
    """오늘의 재테크/경제/투자 트렌드 수집"""
    print("\n🔍 [STEP 2] 오늘의 트렌드 수집 중...")

    categories = {
        "주식 & ETF":      "주식 ETF 투자 오늘 이슈 급등 급락",
        "부동산 & 절세":    "부동산 세금 청약 절세 최신 뉴스",
        "경제 & 금융 트렌드": "금리 환율 인플레이션 재테크 MZ 트렌드",
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
            time.sleep(1.2)

    except Exception as e:
        print(f"  ⚠️  웹 서치 실패 ({e}) → 기본 트렌드 사용")
        trends = {
            "주식 & ETF": [
                {"title": "ETF 투자 입문 가이드", "snippet": "초보자도 쉽게 시작할 수 있는 ETF 투자 방법이 화제입니다.", "url": ""},
                {"title": "배당주 투자 트렌드", "snippet": "월배당 ETF에 대한 관심이 높아지고 있습니다.", "url": ""},
            ],
            "부동산 & 절세": [
                {"title": "청약 당첨 전략", "snippet": "2024년 청약 제도 변경 사항과 당첨 노하우가 공유되고 있습니다.", "url": ""},
                {"title": "IRP·ISA 절세 활용법", "snippet": "연말정산 절세를 위한 IRP, ISA 활용법이 인기입니다.", "url": ""},
            ],
            "경제 & 금융 트렌드": [
                {"title": "금리 인하 시대 재테크 전략", "snippet": "금리 변화에 따른 포트폴리오 조정 방법이 화제입니다.", "url": ""},
                {"title": "MZ세대 재테크 트렌드", "snippet": "20-30대의 재테크 방식이 기성세대와 달라지고 있습니다.", "url": ""},
            ],
        }

    return trends


# ══════════════════════════════════════════
# STEP 3 — Claude API로 아이디어 20개 생성
# ══════════════════════════════════════════

def build_prompt(patterns: dict, trends: dict) -> str:
    today = datetime.now().strftime("%Y년 %m월 %d일")

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

    trend_lines = []
    for cat, items in trends.items():
        trend_lines.append(f"\n**{cat}:**")
        for item in items:
            trend_lines.append(f"  - {item['title']}: {item['snippet'][:120]}")
    trend_section = "\n".join(trend_lines)

    return f"""당신은 10년 경력의 재테크 콘텐츠 디렉터입니다. 오늘({today}) 재테크 인스타그램 계정을 위한 릴스 아이디어 20개를 생성해주세요.

## 계정 DNA
- **타겟:** 20-30대 직장인, 사회초년생, 재테크 입문자
- **주제:** 주식/ETF 투자 / 부동산 청약 / 절세 전략 (IRP·ISA·연말정산) / 통장 관리 / 소비 습관 / 경제 뉴스 해석
- **톤앤매너:** 친절한 선배 느낌 — 어렵지 않게, "이거 나만 알기 아까워서" 느낌, 복잡한 금융 용어는 쉽게 풀어서, 절대 강요하거나 과장하지 않음
- **훅 스타일:** 공감형, 숫자 자극형, "몰랐지?" 형 — 항상 구체적인 금액/숫자 포함 선호

{pattern_section}

## 오늘의 트렌드
{trend_section}

## 아이디어 20개 생성 규칙
- 최소 6개: 주식/ETF/펀드 투자 (구체적인 상품명 또는 전략 명시)
- 최소 4개: 절세/세금 (IRP, ISA, 연말정산, 증여세 등)
- 최소 4개: 돈 관리 / 통장 쪼개기 / 소비 습관
- 최소 3개: 부동산 / 청약 / 전월세
- 나머지 3개: 오늘 트렌드 반응형 (위 트렌드 데이터 기반)

## 출력 형식 (정확히 이 형식을 따를 것, 20개 모두)

---

**아이디어 #N**

1. **아이디어 제목:** [짧고 강렬한 제목]
2. **후킹 카피 (첫 3초):** [스크롤 멈추게 하는 한 문장 — 구체적인 숫자나 공감 포인트 포함]
3. **촬영 연출:** [구체적인 장면 묘사 — 화면에 무엇이 보이는지, 동작, 텍스트 오버레이. 스마트폰만 사용.]
4. **본문 카피 요약:** [2-4문장. 핵심 정보 먼저. 구체적인 숫자/금액 포함. 쉬운 말로.]
5. **CTA:** [한 줄. 적절하면 "댓글에 'OOO' 남겨주시면 자료 보내드립니다!" 패턴 적용.]

---

**중요 원칙:**
- 썸네일 패턴: 숫자형 / 질문형 / 비교·충격형 / 내부자팁형 / "모르면 손해"형 골고루 활용
- 모든 아이디어는 스마트폰만으로 즉시 촬영 가능해야 함
- 과장된 수익률 보장이나 특정 종목 강력 추천은 절대 금지
- 어려운 금융 용어는 반드시 쉽게 풀어서 설명
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
        html += f'<h3 style="color:#2E7D32;margin:16px 0 8px;font-size:15px;">{cat}</h3>'
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
    import re
    html = ideas_raw
    html = re.sub(r"\n---\n", '\n<hr style="border:none;border-top:1px solid #EBEBEB;margin:24px 0;">\n', html)
    html = re.sub(
        r"\*\*(아이디어 #\d+)\*\*",
        r'<h3 style="color:#1a1a1a;font-size:16px;margin:20px 0 12px;">💰 \1</h3>',
        html
    )
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = html.replace("\n", "<br>")
    return html


def build_email_html(sheet_success: bool, trends: dict, ideas: str) -> str:
    today_kr    = datetime.now().strftime("%Y년 %m월 %d일")
    now_str     = datetime.now().strftime("%Y년 %m월 %d일 %H:%M")
    data_status = "✅ 실시간 시트 데이터 반영" if sheet_success else "⚠️ 폴백 데이터 사용"

    return f"""<!DOCTYPE html>
<html><body style="font-family:'Apple SD Gothic Neo',Arial,sans-serif;max-width:720px;margin:auto;padding:24px;color:#1a1a1a;background:#fff;">

  <h2 style="color:#2D2D2D;border-bottom:3px solid #2E7D32;padding-bottom:10px;margin-bottom:20px;">
    💰 재테크 릴스 아이디어 20개 — {today_kr}
  </h2>

  <div style="background:#F1F8E9;border-left:4px solid #2E7D32;padding:10px 16px;margin-bottom:28px;border-radius:4px;">
    <p style="margin:0;font-size:14px;"><strong>데이터 상태:</strong> {data_status}</p>
  </div>

  <h2 style="color:#2D2D2D;font-size:18px;border-bottom:2px solid #EBEBEB;padding-bottom:8px;margin-bottom:16px;">
    📈 오늘의 재테크 트렌드
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
    자동 생성 — {now_str} | finance_reels_planner.py
  </p>

</body></html>"""


def send_gmail(subject: str, html_body: str):
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
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        path = os.path.join(OUTPUT_DIR, f"reels-finance-{today_str}.md")
    except Exception:
        output_dir_local = os.path.expanduser("~/reels_outputs")
        os.makedirs(output_dir_local, exist_ok=True)
        path = os.path.join(output_dir_local, f"reels-finance-{today_str}.md")

    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# 재테크 릴스 아이디어 20개 — {today_str}\n\n")
        f.write(ideas)
    print(f"  💾 폴백 저장 완료: {path}")


# ══════════════════════════════════════════
# 메인
# ══════════════════════════════════════════

def main():
    today_str = datetime.now().strftime("%Y-%m-%d")
    print(f"\n{'='*55}")
    print(f"  🚀 재테크 릴스 플래너 시작 — {today_str}")
    print(f"{'='*55}\n")

    patterns, sheet_success = fetch_sheet_data()
    trends = search_trends()
    ideas  = generate_ideas(patterns, trends)

    subject   = f"[재테크 릴스] 오늘의 아이디어 20개 — {today_str}"
    html_body = build_email_html(sheet_success, trends, ideas)

    try:
        send_gmail(subject, html_body)
    except Exception as e:
        print(f"  ❌ Gmail 발송 실패: {e} → 파일 저장으로 대체")
        save_fallback(ideas, today_str)

    print(f"\n{'='*55}")
    print("  ✅ 재테크 릴스 플래너 완료!")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
