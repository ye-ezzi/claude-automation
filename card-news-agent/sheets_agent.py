"""
구글시트 읽기/쓰기 모듈 — 채널별 동적 컬럼 구조

컬럼 구조는 config.yaml의 각 채널 card01_fields / body_fields 에 따라 결정됩니다.
공통 prefix: 날짜, 폴더명, 페르소나, 욕구, 인지단계, 펀넬, 앵글, 기획법
공통 suffix: 컨셉, 기대반응, 본문 상태, PNG 폴더
"""

import os
from pathlib import Path

import yaml
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

BASE = Path(__file__).parent
load_dotenv(BASE / ".env", override=True)

COMMON_PREFIX = ["날짜", "폴더명", "페르소나", "욕구", "인지단계", "펀넬", "앵글", "기획법"]
COMMON_SUFFIX = ["컨셉", "기대반응", "본문 상태", "PNG 폴더"]

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def load_config() -> dict:
    with open(BASE / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_header(channel_cfg: dict) -> list:
    """채널 설정에서 헤더 컬럼 목록 생성"""
    card01 = [f"Card01 {f['name']}" for f in channel_cfg["card01_fields"]]
    n_body = channel_cfg.get("body_cards", 3)
    body = []
    for i in range(2, 2 + n_body):
        for f in channel_cfg["body_fields"]:
            body.append(f"Card{i:02d} {f['name']}")
    cta = ["Card05 CTA 유도문구"]
    return COMMON_PREFIX + card01 + ["썸네일 상태"] + body + cta + COMMON_SUFFIX


def get_col(header: list) -> dict:
    return {h: i for i, h in enumerate(header)}


def _get_client() -> gspread.Client:
    creds_path = os.environ.get("CREDENTIALS_PATH", str(BASE / "credentials.json"))
    creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    return gspread.authorize(creds)


def get_worksheet(tab_name: str) -> tuple:
    """워크시트와 헤더 반환"""
    client = _get_client()
    spreadsheet_id = os.environ.get("SPREADSHEET_ID", "")
    spreadsheet = client.open_by_key(spreadsheet_id)
    ws = spreadsheet.worksheet(tab_name)
    return ws


def read_pending_rows(tab_name: str, channel_cfg: dict) -> list:
    """본문 상태 = '대기중'인 행 반환 [(row_index, row_dict), ...]"""
    ws = get_worksheet(tab_name)

    all_values = ws.get_all_values()
    if not all_values:
        return []

    # 시트의 실제 헤더 사용 (코드 헤더가 아닌)
    sheet_header = all_values[0]
    col = {h: i for i, h in enumerate(sheet_header)}

    print(f"  시트 컬럼 수: {len(sheet_header)}개")

    # 본문 상태 컬럼 찾기
    status_col = col.get("본문 상태")
    if status_col is None:
        print(f"  ⚠️  '본문 상태' 컬럼이 시트에 없습니다. 컬럼 목록: {sheet_header}")
        return []

    pending = []
    # Card02 첫 번째 필드 컬럼 찾기 (이미 내용 있으면 스킵)
    card02_col = next((col[h] for h in sheet_header if h.startswith("Card02")), None)

    for i, row in enumerate(all_values[1:], start=2):
        row_padded = row + [""] * (len(sheet_header) - len(row))
        status = row_padded[status_col]

        if status == "본문 대기":
            # Card02 이미 채워져 있으면 스킵
            if card02_col is not None and row_padded[card02_col].strip():
                print(f"  ⏭️  {i}행: Card02 이미 있음 — 스킵 ({row_padded[1]})")
                continue
            row_dict = {h: row_padded[j] for j, h in enumerate(sheet_header)}
            pending.append((i, row_dict))

    return pending


def write_generated(tab_name: str, row_index: int, updates: dict, channel_cfg: dict):
    """생성된 내용을 시트의 특정 행에 업데이트"""
    ws = get_worksheet(tab_name)

    # 시트의 실제 헤더 사용
    sheet_header = ws.row_values(1)
    col = {h: i for i, h in enumerate(sheet_header)}

    cell_updates = []
    for key, value in updates.items():
        if key in col:
            col_letter = gspread.utils.rowcol_to_a1(row_index, col[key] + 1)
            cell_updates.append({"range": col_letter, "values": [[value]]})

    if cell_updates:
        ws.spreadsheet.values_batch_update({
            "valueInputOption": "USER_ENTERED",
            "data": cell_updates
        })
        print(f"  ✅ {row_index}행 업데이트 완료 ({len(cell_updates)}개 셀)")
