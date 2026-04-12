"""
카드뉴스 자동생성 FastAPI 서버

구글 시트에서 완성된 카드 내용을 읽어 Figma 플러그인에 전달.

실행:
  source venv/bin/activate
  python3 server.py
  → http://localhost:8000

엔드포인트:
  GET  /health              - 서버 상태 확인
  GET  /config              - 채널 목록
  GET  /rows?channel=재테크  - 해당 채널 시트의 폴더명 목록
  GET  /row?channel=재테크&folder=ISA계좌  - 해당 행 전체 데이터
"""

import os
from pathlib import Path

import uvicorn
import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

BASE = Path(__file__).parent
load_dotenv(BASE / ".env", override=True)

app = FastAPI(title="카드뉴스 Figma 연동 API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def load_config() -> dict:
    with open(BASE / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_worksheet(tab_name: str):
    from sheets_agent import _get_client
    client = _get_client()
    spreadsheet_id = os.environ.get("SPREADSHEET_ID", "")
    spreadsheet = client.open_by_key(spreadsheet_id)
    return spreadsheet.worksheet(tab_name)


# ─── 엔드포인트 ───────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/config")
def get_config():
    """채널 목록 반환"""
    cfg = load_config()
    return {"channels": list(cfg.get("channels", {}).keys())}


@app.get("/rows")
def get_rows(channel: str = Query(..., description="채널명 (예: 재테크)")):
    """해당 채널 시트에서 폴더명 목록 반환"""
    cfg = load_config()
    channels = cfg.get("channels", {})
    if channel not in channels:
        raise HTTPException(status_code=400, detail=f"채널 '{channel}'이 없습니다.")

    tab = channels[channel]["sheet_tab"]
    try:
        ws = get_worksheet(tab)
        all_values = ws.get_all_values()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"시트 읽기 실패: {e}")

    if not all_values:
        return []

    header = all_values[0]
    folder_idx = next((i for i, h in enumerate(header) if h == "폴더명"), None)
    if folder_idx is None:
        raise HTTPException(status_code=500, detail="'폴더명' 컬럼을 찾을 수 없습니다.")

    rows = []
    for i, row in enumerate(all_values[1:], start=2):
        padded = row + [""] * (len(header) - len(row))
        folder = padded[folder_idx].strip()
        if folder:
            rows.append({"row": i, "폴더명": folder})

    return rows


@app.get("/row")
def get_row(
    channel: str = Query(..., description="채널명"),
    folder: str = Query(..., description="폴더명(주제)")
):
    """해당 채널+폴더명의 행 데이터 반환

    응답:
      data      - 시트 전체 컬럼 데이터 (key: 컬럼명, value: 셀값)
      fieldOrder - 카드별 필드 순서 (config.yaml body_fields 기준)
                   Figma 플러그인이 위→아래 순서로 텍스트레이어 채울 때 사용
    """
    cfg = load_config()
    channels = cfg.get("channels", {})
    if channel not in channels:
        raise HTTPException(status_code=400, detail=f"채널 '{channel}'이 없습니다.")

    channel_cfg = channels[channel]
    tab = channel_cfg["sheet_tab"]
    try:
        ws = get_worksheet(tab)
        all_values = ws.get_all_values()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"시트 읽기 실패: {e}")

    if not all_values:
        raise HTTPException(status_code=404, detail="시트가 비어 있습니다.")

    header = all_values[0]
    folder_idx = next((i for i, h in enumerate(header) if h == "폴더명"), None)
    if folder_idx is None:
        raise HTTPException(status_code=500, detail="'폴더명' 컬럼을 찾을 수 없습니다.")

    row_data = None
    for row in all_values[1:]:
        padded = row + [""] * (len(header) - len(row))
        if padded[folder_idx].strip() == folder.strip():
            row_data = {header[i]: padded[i] for i in range(len(header))}
            break

    if row_data is None:
        raise HTTPException(status_code=404, detail=f"'{folder}' 항목을 찾을 수 없습니다.")

    # 카드별 필드 순서 (마스터_본문_N 프레임에 위→아래로 채울 순서)
    body_fields = [f["name"] for f in channel_cfg.get("body_fields", [])]
    n_body = channel_cfg.get("body_cards", 3)
    field_order = {}
    for i in range(n_body):
        card_key = f"Card{i + 2:02d}"  # Card02, Card03, Card04
        field_order[card_key] = body_fields

    return {"data": row_data, "fieldOrder": field_order}


if __name__ == "__main__":
    print("🚀 카드뉴스 Figma 연동 서버 시작")
    print("   http://localhost:8000")
    print("   http://localhost:8000/docs  ← API 문서")
    uvicorn.run(app, host="0.0.0.0", port=8000)
