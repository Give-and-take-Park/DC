# DC - Data Collection & Dashboard

사용자 PC의 GUI 프로그램에서 데이터를 수집하여 서버로 전송하고,
정규화된 데이터를 MariaDB에 저장한 뒤 웹 대시보드로 조회하는 시스템.

## 기술 스택

| 영역 | 기술 |
|------|------|
| GUI 클라이언트 | Python + PyQt6 → `.exe` (PyInstaller) |
| API 서버 | Python + FastAPI + SQLAlchemy |
| DB | MariaDB 11 |
| 웹 대시보드 | HTML / CSS / JavaScript |
| 인프라 | Docker Compose |

## 빠른 시작

```bash
# 1. MariaDB + API 서버 실행 (Docker)
cd docker && docker compose up -d

# 2. 서버 단독 실행 (로컬)
cd server && pip install -r requirements.txt
cp .env.example .env   # DB 접속 정보 수정
alembic upgrade head
uvicorn app.main:app --reload

# 3. 클라이언트 실행
cd client && pip install -r requirements.txt
python app/main.py
```

## 문서

- [아키텍처 상세 설명](docs/architecture.md)

## 프로젝트 구조

```
DC/
├── client/   # PyQt6 GUI 클라이언트 (exe)
├── server/   # FastAPI 백엔드 서버
├── web/      # 웹 대시보드 (템플릿 + 정적 파일)
├── db/       # DB 스키마 및 시드 데이터
├── docs/     # 문서
└── docker/   # Docker Compose 설정
```
