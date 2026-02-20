#!/usr/bin/env bash
# DC 서버 가상환경 초기 설정 스크립트
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$PROJECT_ROOT/.venv"

echo "=== DC MLCC Server 환경 설정 ==="
echo "프로젝트 루트: $PROJECT_ROOT"

# Python 3.11+ 확인
python3 -c "import sys; assert sys.version_info >= (3,11), 'Python 3.11 이상이 필요합니다.'" \
  || { echo "오류: Python 3.11+ 을 설치하세요."; exit 1; }

# 가상환경 생성
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    echo "가상환경 생성: $VENV_DIR"
else
    echo "가상환경 이미 존재: $VENV_DIR"
fi

# 의존성 설치
"$VENV_DIR/bin/pip" install --upgrade pip --quiet
"$VENV_DIR/bin/pip" install -r "$PROJECT_ROOT/server/requirements.txt" --quiet
echo "서버 의존성 설치 완료"

# .env 파일 생성
if [ ! -f "$PROJECT_ROOT/server/.env" ]; then
    cp "$PROJECT_ROOT/server/.env.example" "$PROJECT_ROOT/server/.env"
    echo ""
    echo "⚠  server/.env 파일이 생성되었습니다. DB 접속 정보를 설정하세요:"
    echo "   $PROJECT_ROOT/server/.env"
fi

echo ""
echo "완료. 다음 명령으로 서버를 실행하세요:"
echo "  bash scripts/start_server.sh"
