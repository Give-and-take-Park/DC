#!/usr/bin/env bash
# DC 서버 실행 스크립트 (개발용 --reload 포함)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$PROJECT_ROOT/.venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "가상환경이 없습니다. 먼저 다음을 실행하세요:"
    echo "  bash scripts/setup_server.sh"
    exit 1
fi

if [ ! -f "$PROJECT_ROOT/server/.env" ]; then
    echo "server/.env 파일이 없습니다. DB 접속 정보를 설정하세요:"
    echo "  cp server/.env.example server/.env"
    exit 1
fi

echo "=== DC MLCC Server 시작 ==="
cd "$PROJECT_ROOT/server"
"$VENV_DIR/bin/uvicorn" app.main:app --host 0.0.0.0 --port 8000 --reload
