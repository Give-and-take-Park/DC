#!/usr/bin/env bash
# DC 클라이언트 가상환경 초기 설정 스크립트
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$PROJECT_ROOT/client/.venv"

echo "=== DC MLCC Client 환경 설정 ==="
echo "프로젝트 루트: $PROJECT_ROOT"

python3 -c "import sys; assert sys.version_info >= (3,11), 'Python 3.11 이상이 필요합니다.'" \
  || { echo "오류: Python 3.11+ 을 설치하세요."; exit 1; }

if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    echo "클라이언트 가상환경 생성: $VENV_DIR"
else
    echo "가상환경 이미 존재: $VENV_DIR"
fi

"$VENV_DIR/bin/pip" install --upgrade pip --quiet
"$VENV_DIR/bin/pip" install -r "$PROJECT_ROOT/client/requirements.txt" --quiet
echo "클라이언트 의존성 설치 완료"

echo ""
echo "완료. 다음 명령으로 클라이언트를 실행하세요:"
echo "  client/.venv/bin/python client/app/main.py"
echo ""
echo "참고: GPIB 통신에는 NI-VISA 또는 pyvisa-py 백엔드가 필요합니다."
echo "  NI-VISA (권장): https://www.ni.com/en/support/downloads/drivers/download.ni-visa.html"
echo "  pyvisa-py (무료): pip install pyvisa-py 로 설치됩니다."
