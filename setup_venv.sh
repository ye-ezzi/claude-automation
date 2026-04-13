#!/bin/bash
# setup_venv.sh
# 가상환경 생성 + 필요 패키지 자동 설치

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/venv"

echo "=== Python 가상환경 설정 ==="

# Python 3.10+ 자동 감지 (yt-dlp 권장 버전)
PYTHON_BIN=""
for PY in python3.12 python3.11 python3.10 python3; do
    if command -v "$PY" &>/dev/null; then
        PYTHON_BIN="$PY"
        break
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "❌ Python3를 찾을 수 없습니다."
    exit 1
fi

PY_VERSION=$("$PYTHON_BIN" --version 2>&1)
echo "    사용할 Python: $PYTHON_BIN ($PY_VERSION)"

# 가상환경 생성
if [ ! -d "$VENV_DIR" ]; then
    echo "[1/3] 가상환경 생성 중... (${VENV_DIR})"
    "$PYTHON_BIN" -m venv "$VENV_DIR"
    echo "      완료"
else
    echo "[1/3] 기존 가상환경 재사용: ${VENV_DIR}"
fi

# 가상환경 활성화
source "${VENV_DIR}/bin/activate"

# pip 최신화
echo "[2/3] pip 업그레이드 중..."
pip install --upgrade pip --quiet

# 패키지 설치
echo "[3/3] 패키지 설치 중..."
pip install -r "${SCRIPT_DIR}/requirements.txt"

# yt-dlp 최신 버전으로 업그레이드 (Instagram 호환성)
echo "    yt-dlp 최신화 중..."
pip install -U yt-dlp --quiet

echo ""
echo "=== 설치 완료 ==="
echo "앞으로 스크립트는 자동으로 가상환경을 사용합니다."
echo "수동 실행 시: source venv/bin/activate && python3 reels_translator.py"
