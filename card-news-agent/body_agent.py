"""
카드뉴스 본문 자동 생성 — Claude API 사용

기획법(HIRA/HOS/PASO/PAF/BAD/LIST/기본)에 따라
Card02~04 섹션 내용과 Card05 CTA, 컨셉, 기대반응을 생성합니다.
"""

import json
import os
from pathlib import Path

import anthropic
from dotenv import load_dotenv

BASE = Path(__file__).parent
load_dotenv(BASE / ".env", override=True)

# 기획법별 카드 구조 설명
FRAMEWORK_GUIDE = {
    "HIRA": {
        "desc": "Hook → Insight → Reveal → Action",
        "cards": {
            "Card02": "Hook — 공감 또는 충격적 사실로 주의 잡기",
            "Card03": "Insight — 핵심 인사이트/정보 전달",
            "Card04": "Reveal + Action — 반전 또는 구체적 실천 방법",
        }
    },
    "HOS": {
        "desc": "Hook → Offer → Story",
        "cards": {
            "Card02": "Hook — 강렬한 첫 질문 또는 공감 포인트",
            "Card03": "Offer — 핵심 제안/솔루션",
            "Card04": "Story — 실제 사례 또는 스토리로 설득",
        }
    },
    "PASO": {
        "desc": "Problem → Agitation → Solution → Offer",
        "cards": {
            "Card02": "Problem — 타겟이 겪는 구체적 문제",
            "Card03": "Agitation + Solution — 문제를 더 와닿게 → 해결책",
            "Card04": "Offer — 구체적인 실천 제안",
        }
    },
    "PAF": {
        "desc": "Problem → Agitation → Fix",
        "cards": {
            "Card02": "Problem — 문제 제기",
            "Card03": "Agitation — 그대로 두면 어떻게 되는지 불안 자극",
            "Card04": "Fix — 명확하고 간단한 해결법",
        }
    },
    "BAD": {
        "desc": "Before → After → Difference (변화 강조형)",
        "cards": {
            "Card02": "Before — 변화 전의 상황/문제",
            "Card03": "After — 변화 후의 모습/결과",
            "Card04": "Difference — 무엇이 달라졌는지 핵심 차이",
        }
    },
    "LIST": {
        "desc": "숫자 리스트형 (3가지, 5단계 등)",
        "cards": {
            "Card02": "리스트 항목 1~2 — 첫 번째, 두 번째 포인트",
            "Card03": "리스트 항목 3~4 — 세 번째, 네 번째 포인트",
            "Card04": "리스트 항목 5 + 정리 — 마지막 포인트와 핵심 요약",
        }
    },
    "기본": {
        "desc": "자유 구성",
        "cards": {
            "Card02": "핵심 내용 1",
            "Card03": "핵심 내용 2",
            "Card04": "핵심 내용 3 + 정리",
        }
    },
}


def build_prompt(row: dict, channel_cfg: dict) -> str:
    """생성 프롬프트 작성"""
    framework = row.get("기획법", "기본")
    fw = FRAMEWORK_GUIDE.get(framework, FRAMEWORK_GUIDE["기본"])

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
- 인지단계: {row.get('인지단계', '')}
- 펀넬: {row.get('펀넬', '')}
- 앵글: {row.get('앵글', '')}
- 기획법: {framework} ({fw['desc']})
- Card01 헤드라인: {row.get('Card01 헤드라인', '')}

## 기획법 구조 ({framework})
{card_roles}

## 각 카드의 필드
{fields_guide}

## 출력 규칙
- Card02, Card03, Card04 각각에 대해 아래 필드를 생성하세요
- Card05 CTA 유도문구: 저장/공유/댓글 행동 유도 (1줄)
- 컨셉: 이 카드뉴스의 핵심 메시지 (1문장)
- 기대반응: 독자의 기대 반응 (예: "나도 해봐야겠다 / 저장")

## 출력 형식 (JSON)
반드시 아래 JSON 형식으로만 출력하세요. 다른 텍스트 없이 JSON만:

{{
  "Card02": {{{", ".join(f'"{n}": "..."' for n in field_names)}}},
  "Card03": {{{", ".join(f'"{n}": "..."' for n in field_names)}}},
  "Card04": {{{", ".join(f'"{n}": "..."' for n in field_names)}}},
  "Card05 CTA 유도문구": "...",
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
- 인지단계: {row.get('인지단계', '')}
- 펀넬: {row.get('펀넬', '')}
- 앵글: {row.get('앵글', '')}
- 기획법: {row.get('기획구조', row.get('기획법', '기본'))}

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

    # Card01 헤드라인 비어있으면 먼저 생성
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

    print(f"  🤖 Claude 생성 중... (기획법: {row.get('기획구조', row.get('기획법', '기본'))})")

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()

    # JSON 파싱
    try:
        # ```json ... ``` 블록 제거
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw.strip())
    except json.JSONDecodeError as e:
        print(f"  ⚠️  JSON 파싱 실패: {e}")
        print(f"  원본 응답: {raw[:200]}")
        return {}

    # 플랫 구조로 변환 (Card02 섹션타이틀, Card02 섹션텍스트, ...)
    result = {}
    for card_key in ["Card02", "Card03", "Card04"]:
        if card_key in data:
            for field, value in data[card_key].items():
                result[f"{card_key} {field}"] = value

    result["Card05 CTA 유도문구"] = data.get("Card05 CTA 유도문구", "")
    result["컨셉"] = data.get("컨셉", "")
    result["기대반응"] = data.get("기대반응", "")
    result["본문 상태"] = "완료"

    return result
