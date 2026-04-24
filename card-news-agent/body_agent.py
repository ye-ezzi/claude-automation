"""
카드뉴스 본문 자동 생성 — Claude API 사용

기획법(HIRA/PAF/MRC/BAD/QQA/SCS/LES/FRF/EME/TWH/HOS/PASO)에 따라
Card02~05 섹션 내용과 Card06 CTA, 컨셉, 기대반응을 생성합니다.
기획법이 비어있으면 페르소나+욕구를 분석해 자동 선택합니다.
"""

import json
import os
from pathlib import Path

import anthropic
from dotenv import load_dotenv

BASE = Path(__file__).parent
load_dotenv(BASE / ".env", override=True)

FRAMEWORK_GUIDE = {
    "HIRA": {
        "structure": "Hook → Interest Loop → Reveal → Action",
        "purpose": "체류시간 극대화 + 저장·공유 동시 유도",
        "cards": {
            "Card02": "Hook — 당연하다고 믿는 것을 하고 있는데 예상치 못한 문제가 생긴다는 훅",
            "Card03": "Interest Loop — 왜 이 문제가 반복되는지 질문을 던지며 궁금증 유지",
            "Card04": "Reveal — 진짜 원인은 기존에 생각하던 것이 아님을 밝힘",
            "Card05": "Action — 구체적 실천 방법 + 저장 유도",
        }
    },
    "PAF": {
        "structure": "Problem → Agitation → Fix",
        "purpose": "문제 인식 강화 + 행동 변화 유도",
        "cards": {
            "Card02": "Problem — 타겟이 겪는 구체적 문제 제기",
            "Card03": "Agitation — 이 방식 계속 가면 생기는 구체적 손해, 불안 자극",
            "Card04": "Fix — 잘못된 접근 방식 지적 + 새로운 기준 제시",
            "Card05": "Result — 올바른 방법으로 얻을 수 있는 변화/결과",
        }
    },
    "MRC": {
        "structure": "Myth → Reality → Conclusion",
        "purpose": "인식 전환 + 전문가 포지셔닝",
        "cards": {
            "Card02": "Myth — 대부분이 사실이라고 믿는 잘못된 상식",
            "Card03": "Reality — 실제 데이터나 사례로 반전",
            "Card04": "Conclusion — 새로운 프레임/기준 제시",
            "Card05": "Action — 이 인식을 바탕으로 지금 할 수 있는 것",
        }
    },
    "BAD": {
        "structure": "Before → After → Difference",
        "purpose": "신뢰 확보 + 팔로우 전환",
        "cards": {
            "Card02": "Before — 변화 전 반복되던 문제 상황",
            "Card03": "After — 변화 후 눈에 보이는 결과",
            "Card04": "Difference — 바뀐 것은 딱 하나, 결정적 차이",
            "Card05": "Action — 독자가 지금 당장 시작할 수 있는 첫 번째 행동",
        }
    },
    "QQA": {
        "structure": "Question → Question → Answer",
        "purpose": "궁금증 유발 + 넘김 유도",
        "cards": {
            "Card02": "Question 1 — 현상에 대한 첫 번째 질문으로 흥미 유발",
            "Card03": "Question 2 — 더 깊은 질문으로 표면적 이유를 의심하게 만들기",
            "Card04": "Answer — 이유는 단 하나, 핵심 원인 명확히 제시",
            "Card05": "Application — 이 답을 바탕으로 독자가 적용할 수 있는 것",
        }
    },
    "SCS": {
        "structure": "Situation → Conflict → Solution",
        "purpose": "신뢰 형성 + 브랜드 서사 구축",
        "cards": {
            "Card02": "Situation — 처음 무작정 시도했던 상황",
            "Card03": "Conflict — 반복된 문제와 실패",
            "Card04": "Solution — 의외의 원인 발견과 해결",
            "Card05": "Lesson — 이 경험에서 얻은 핵심 인사이트",
        }
    },
    "LES": {
        "structure": "List → Explanation → Summary",
        "purpose": "정보 정리 + 체크리스트 제공 (저장률 최고)",
        "cards": {
            "Card02": "List 항목 1~2 — 첫 번째, 두 번째 포인트 + 핵심 설명",
            "Card03": "List 항목 3~4 — 세 번째, 네 번째 포인트 + 핵심 설명",
            "Card04": "List 항목 5~6 — 다섯 번째, 여섯 번째 포인트 + 핵심 설명",
            "Card05": "Summary — 이것만 지켜도 결과가 달라진다는 정리",
        }
    },
    "FRF": {
        "structure": "Fact → Reason → Framework",
        "purpose": "전문성 증명 + 신뢰 확보",
        "cards": {
            "Card02": "Fact — 구체적인 수치나 성과",
            "Card03": "Reason — 그 성과가 나온 구조적 원인",
            "Card04": "Framework — 재현 가능한 3단계 또는 공식",
            "Card05": "Application — 독자가 이 프레임워크를 적용하는 방법",
        }
    },
    "EME": {
        "structure": "Experience → Meaning → Expansion",
        "purpose": "공감 형성 + 팬화",
        "cards": {
            "Card02": "Experience — 나도 겪었던 정체·실패 경험",
            "Card03": "Meaning — 그때 깨달은 의외의 인사이트",
            "Card04": "Expansion — 이 이야기가 독자에게 중요한 이유",
            "Card05": "Action — 독자가 지금 바로 시작할 수 있는 것",
        }
    },
    "TWH": {
        "structure": "This → Why → How",
        "purpose": "신규 유입 + 빠른 이해",
        "cards": {
            "Card02": "This — 핵심 주장 한 문장으로",
            "Card03": "Why — 왜 이것이 중요한지 이유",
            "Card04": "How — 구체적으로 어떻게 하는지",
            "Card05": "Summary — 핵심 정리 + 저장 유도",
        }
    },
    "HOS": {
        "structure": "Hook → Offer → Solution",
        "purpose": "전환율 극대화 + 구매/신청 유도",
        "cards": {
            "Card02": "Hook — 강렬한 훅으로 관심 잡기 (문제 또는 욕구 자극)",
            "Card03": "Offer — 핵심 제안/가치 먼저 제시 (이걸 얻을 수 있다)",
            "Card04": "Solution — 어떻게 가능한지 구체적 솔루션",
            "Card05": "Close — 신뢰 강화 + 행동 유도",
        }
    },
    "PASO": {
        "structure": "Problem → Agitate → Solution → Offer",
        "purpose": "전환율 높은 설득 구조",
        "cards": {
            "Card02": "Problem — 타겟이 겪는 구체적 문제",
            "Card03": "Agitate — 그 문제를 그대로 두면 생기는 더 큰 손해/불안 자극",
            "Card04": "Solution — 문제를 해결하는 명확한 방법 제시",
            "Card05": "Offer — 지금 바로 실천할 수 있는 구체적 제안",
        }
    },
}

FRAMEWORK_LIST = "\n".join(
    f"- {k}: {v['structure']} / 목적: {v['purpose']}"
    for k, v in FRAMEWORK_GUIDE.items()
)


def select_framework(row: dict, channel_cfg: dict, client: anthropic.Anthropic) -> str:
    """페르소나+욕구+폴더명 기반으로 최적 기획법 1개 자동 선택"""
    prompt = f"""카드뉴스 기획법을 선택해주세요.

## 콘텐츠 정보
- 채널 타겟: {channel_cfg.get('target', '')}
- 폴더명(주제): {row.get('폴더명', '')}
- 페르소나: {row.get('페르소나', '')}
- 욕구: {row.get('욕구', '')}

## 선택 가능한 기획법
{FRAMEWORK_LIST}

## 선택 기준
1. 독자의 욕구 유형 파악 (불안/해결 → PAF/MRC, 정보/학습 → LES/TWH, 변화/성과 → BAD/FRF, 공감/서사 → SCS/EME, 호기심 → QQA/HIRA)
2. 페르소나의 현재 상태 파악 (문제 인식 전 → HIRA/TWH, 탐색 중 → MRC/LES, 설득 필요 → PAF/BAD)
3. 채널 타겟과 톤에 맞는 구조 선택

반드시 위 기획법 중 정확히 1개의 이름만 출력하세요. 설명 없이 이름만:"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=10,
        messages=[{"role": "user", "content": prompt}],
    )
    selected = message.content[0].text.strip().upper()
    if selected not in FRAMEWORK_GUIDE:
        return "HIRA"
    return selected


def build_prompt(row: dict, channel_cfg: dict) -> str:
    framework = row.get("기획법", "HIRA")
    fw = FRAMEWORK_GUIDE.get(framework, FRAMEWORK_GUIDE["HIRA"])

    body_fields = channel_cfg.get("body_fields", [])
    field_names = [f["name"] for f in body_fields]
    field_descs = {f["name"]: f["desc"] for f in body_fields}

    fields_guide = "\n".join(
        f"  - {name}: {field_descs[name]}" for name in field_names
    )
    card_roles = "\n".join(
        f"  - {card}: {role}" for card, role in fw["cards"].items()
    )

    return f"""당신은 카드뉴스 콘텐츠 전문가입니다. 아래 정보를 바탕으로 카드뉴스 본문을 생성해주세요.

## 입력 정보
- 채널 타겟: {channel_cfg.get('target', '')}
- 톤앤매너: {channel_cfg.get('tone', '')}
- 페르소나: {row.get('페르소나', '')}
- 욕구: {row.get('욕구', '')}
- 기획법: {framework} ({fw['structure']})
- 기획법 목적: {fw['purpose']}
- Card01 헤드라인: {row.get('Card01 헤드라인', '')}

## 기획법 구조
{card_roles}

## 각 카드의 필드
{fields_guide}

## 출력 규칙
- Card02, Card03, Card04, Card05 각각에 대해 아래 필드를 생성하세요
- Card06 CTA 유도문구: 저장/공유/댓글 행동 유도 (1줄)
- 컨셉: 이 카드뉴스의 핵심 메시지 (1문장)
- 기대반응: 독자의 기대 반응 (예: "나도 해봐야겠다 / 저장")

## 출력 형식 (JSON)
반드시 아래 JSON 형식으로만 출력하세요. 다른 텍스트 없이 JSON만:

{{
  "Card02": {{{", ".join(f'"{n}": "..."' for n in field_names)}}},
  "Card03": {{{", ".join(f'"{n}": "..."' for n in field_names)}}},
  "Card04": {{{", ".join(f'"{n}": "..."' for n in field_names)}}},
  "Card05": {{{", ".join(f'"{n}": "..."' for n in field_names)}}},
  "Card06 CTA 유도문구": "...",
  "컨셉": "...",
  "기대반응": "..."
}}"""


def generate_card01(row: dict, channel_cfg: dict, client: anthropic.Anthropic) -> dict:
    """Card01 헤드라인 + 컬러칩 자동 생성"""
    card01_fields = channel_cfg.get("card01_fields", [])
    field_descs = {f["name"]: f["desc"] for f in card01_fields}

    fields_guide = "\n".join(
        f"  - {name}: {desc}" for name, desc in field_descs.items()
    )

    prompt = f"""카드뉴스 Card01(표지 카드) 내용을 생성해주세요.

## 입력 정보
- 채널 타겟: {channel_cfg.get('target', '')}
- 톤앤매너: {channel_cfg.get('tone', '')}
- 폴더명(주제): {row.get('폴더명', '')}
- 페르소나: {row.get('페르소나', '')}
- 욕구: {row.get('욕구', '')}
- 기획법: {row.get('기획법', '')}

## 생성할 필드
{fields_guide}

## 출력 형식 (JSON만, 다른 텍스트 없이)
{{{", ".join(f'"Card01 {name}": "..."' for name in field_descs.keys())}}}"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    try:
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        return {}


def generate(row: dict, channel_cfg: dict) -> dict:
    """Claude API로 카드뉴스 본문 생성"""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")

    client = anthropic.Anthropic(api_key=api_key)

    # 기획법 자동 선택 (비어있을 때)
    if not row.get("기획법", "").strip():
        print(f"  🔍 기획법 자동 선택 중...")
        row["기획법"] = select_framework(row, channel_cfg, client)
        print(f"  ✅ 기획법 선택: {row['기획법']}")

    # Card01 비어있으면 먼저 생성
    card01_fields = channel_cfg.get("card01_fields", [])
    for f in card01_fields:
        key = f"Card01 {f['name']}"
        if not row.get(key, "").strip():
            print(f"  📝 Card01 자동 생성 중...")
            card01_data = generate_card01(row, channel_cfg, client)
            row.update(card01_data)
            print(f"  ✅ Card01 헤드라인: {row.get('Card01 헤드라인', '')[:30]}...")
            break

    prompt = build_prompt(row, channel_cfg)
    print(f"  🤖 Claude 생성 중... (기획법: {row.get('기획법', '')})")

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    try:
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw.strip())
    except json.JSONDecodeError as e:
        print(f"  ⚠️  JSON 파싱 실패: {e}")
        print(f"  원본 응답: {raw[:200]}")
        return {}

    result = {}

    # 자동 선택된 기획법 저장
    result["기획법"] = row.get("기획법", "")

    # Card01
    for f in channel_cfg.get("card01_fields", []):
        key = f"Card01 {f['name']}"
        if row.get(key, "").strip():
            result[key] = row[key]

    # Card02~05
    for card_key in ["Card02", "Card03", "Card04", "Card05"]:
        if card_key in data:
            for field, value in data[card_key].items():
                result[f"{card_key} {field}"] = value

    result["Card06 CTA 유도문구"] = data.get("Card06 CTA 유도문구", "")
    result["컨셉"] = data.get("컨셉", "")
    result["기대반응"] = data.get("기대반응", "")
    result["본문 상태"] = "본문 승인"

    return result
