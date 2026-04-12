"""
카드뉴스 자동생성 FastAPI 서버

Figma 플러그인(또는 curl)에서 호출하면 Claude API로 카드 내용을 생성해 반환.

실행:
  source venv/bin/activate
  pip install fastapi uvicorn
  python3 server.py
  → http://localhost:8000

엔드포인트:
  GET  /health   - 서버 상태 확인
  GET  /config   - 채널/기획법/옵션 목록
  POST /generate - 카드 내용 생성
"""

import os
from pathlib import Path

import uvicorn
import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

BASE = Path(__file__).parent
load_dotenv(BASE / ".env", override=True)

app = FastAPI(title="카드뉴스 자동생성 API", version="1.0.0")

# CORS — Figma 플러그인(iframe)이 localhost 호출할 수 있도록 전체 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def load_config() -> dict:
    with open(BASE / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ─── 요청 모델 ─────────────────────────────────────────────
class GenerateRequest(BaseModel):
    channel: str
    폴더명: str = ""
    페르소나: str = ""
    욕구: str = ""
    인지단계: str = ""
    펀넬: str = ""
    앵글: str = ""
    기획법: str = "기본"


# ─── 엔드포인트 ───────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/config")
def get_config():
    """채널 목록, 기획법, 드롭다운 옵션 반환"""
    cfg = load_config()
    channels = list(cfg.get("channels", {}).keys())
    frameworks = list(cfg.get("frameworks", {}).keys())
    options = cfg.get("options", {})
    return {
        "channels": channels,
        "frameworks": frameworks,
        "options": options,
    }


@app.post("/generate")
def generate(req: GenerateRequest):
    """카드 내용 생성"""
    cfg = load_config()
    channels = cfg.get("channels", {})

    if req.channel not in channels:
        raise HTTPException(
            status_code=400,
            detail=f"채널 '{req.channel}'이 없습니다. 사용 가능: {list(channels.keys())}",
        )

    channel_cfg = channels[req.channel]

    # body_agent.generate()가 기대하는 row dict 구성
    row = {
        "폴더명": req.폴더명,
        "페르소나": req.페르소나,
        "욕구": req.욕구,
        "인지단계": req.인지단계,
        "펀넬": req.펀넬,
        "앵글": req.앵글,
        "기획구조": req.기획법,  # 시트 컬럼명과 일치
        "기획법": req.기획법,
    }

    # body_agent 임포트 (런타임에 해서 .env 로드 후 API 키 확인)
    try:
        from body_agent import generate as agent_generate
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"body_agent 임포트 실패: {e}")

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key or api_key.startswith("sk-ant-..."):
        raise HTTPException(
            status_code=500,
            detail="ANTHROPIC_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.",
        )

    result = agent_generate(row, channel_cfg)
    if not result:
        raise HTTPException(status_code=500, detail="카드 내용 생성 실패")

    return result


if __name__ == "__main__":
    print("🚀 카드뉴스 자동생성 서버 시작")
    print("   http://localhost:8000")
    print("   http://localhost:8000/docs  ← API 문서")
    uvicorn.run(app, host="0.0.0.0", port=8000)
