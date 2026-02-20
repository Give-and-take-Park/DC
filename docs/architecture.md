# DC 프로젝트 아키텍처

## 시스템 개요

사용자 PC의 GUI 프로그램에서 데이터를 수집하여 서버로 전송하고,
정규화된 데이터를 DB에 저장한 뒤 웹 대시보드로 조회하는 시스템.

```
┌────────────────────────┐         HTTPS/REST         ┌────────────────────────┐
│   Client (사용자 PC)    │  ─────────────────────────▶ │   Server (FastAPI)     │
│                        │                             │                        │
│  ┌──────────────────┐  │                             │  ┌──────────────────┐  │
│  │  PyQt6 GUI (exe) │  │   POST /api/v1/data         │  │  API Router      │  │
│  │                  │  │  { client_id, payload }     │  │  /data           │  │
│  │  DataCollector   │  │                             │  │  /dashboard      │  │
│  │  APIClient       │  │                             │  └────────┬─────────┘  │
│  └──────────────────┘  │                             │           │            │
└────────────────────────┘                             │  ┌────────▼─────────┐  │
                                                       │  │  DataService     │  │
                                                       │  │  Normalizer      │  │
                                                       │  └────────┬─────────┘  │
                                                       │           │            │
                                                       │  ┌────────▼─────────┐  │
                                                       │  │  CRUD Layer      │  │
                                                       │  │  (SQLAlchemy)    │  │
                                                       │  └────────┬─────────┘  │
                                                       └───────────┼────────────┘
                                                                   │
                                                                   ▼
                                                       ┌────────────────────────┐
                                                       │   MariaDB              │
                                                       │                        │
                                                       │  ┌──────────────────┐  │
                                                       │  │  raw_data        │  │
                                                       │  │  normalized_data │  │
                                                       │  └──────────────────┘  │
                                                       └────────────────────────┘
                                                                   ▲
                                                                   │ GET /api/v1/dashboard
                                                       ┌───────────┴────────────┐
                                                       │   Web Dashboard        │
                                                       │   (Browser)            │
                                                       │                        │
                                                       │  HTML + CSS + JS       │
                                                       │  /templates/dashboard  │
                                                       └────────────────────────┘
```

---

## 컴포넌트별 설명

### 1. Client (PyQt6 GUI)

| 항목 | 내용 |
|------|------|
| 언어/프레임워크 | Python 3.12 + PyQt6 |
| 배포 형태 | PyInstaller로 빌드한 단일 `.exe` |
| 역할 | 사용자 PC의 데이터 수집 → FastAPI 서버로 HTTP 전송 |
| 주요 모듈 | `DataCollector` (수집), `APIClient` (HTTP 전송) |

**데이터 흐름**
1. GUI에서 사용자가 전송 트리거
2. `DataCollector.collect()` → 수집 대상 데이터 딕셔너리 반환
3. `APIClient.send_data()` → `POST /api/v1/data` 호출

---

### 2. Server (FastAPI)

| 항목 | 내용 |
|------|------|
| 언어/프레임워크 | Python 3.12 + FastAPI + Uvicorn |
| DB ORM | SQLAlchemy 2.x |
| 마이그레이션 | Alembic |
| 역할 | 데이터 수신 → 정규화 → DB 저장 / 대시보드 데이터 제공 |

**계층 구조**
```
API Layer     → app/api/v1/endpoints/
Service Layer → app/services/          (비즈니스 로직, 정규화)
CRUD Layer    → app/crud/              (DB 읽기·쓰기)
Model Layer   → app/models/            (SQLAlchemy ORM)
Schema Layer  → app/schemas/           (Pydantic 요청/응답)
```

**주요 엔드포인트**
| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/v1/data` | 클라이언트 데이터 수신 및 저장 |
| GET | `/api/v1/dashboard/summary` | 요약 통계 조회 |
| GET | `/api/v1/dashboard/records` | 데이터 목록 페이지네이션 조회 |

---

### 3. Database (MariaDB)

| 항목 | 내용 |
|------|------|
| DBMS | MariaDB 11 |
| 접속 드라이버 | PyMySQL |

**테이블 구조**

```
raw_data
├── id           INT PK AUTO_INCREMENT
├── client_id    VARCHAR(100)   -- 클라이언트 식별자
├── raw_payload  JSON           -- 원본 데이터
└── received_at  DATETIME

normalized_data
├── id            INT PK AUTO_INCREMENT
├── raw_data_id   INT            -- raw_data 참조
├── client_id     VARCHAR(100)
├── value         DOUBLE         -- 정규화 수치 (도메인별 확장)
├── label         VARCHAR(255)   -- 정규화 레이블
└── normalized_at DATETIME
```

---

### 4. Web Dashboard

| 항목 | 내용 |
|------|------|
| 구성 | FastAPI의 `StaticFiles` + Jinja2 Templates (또는 별도 SPA) |
| 역할 | 정규화 데이터를 브라우저에서 시각화 |
| 경로 | `web/templates/`, `web/static/` |

---

## 프로젝트 폴더 구조

```
DC/
├── client/                        # PyQt6 GUI 클라이언트
│   ├── app/
│   │   ├── main.py                # 진입점
│   │   ├── ui/
│   │   │   ├── main_window.py     # 메인 윈도우
│   │   │   └── widgets/           # 커스텀 위젯
│   │   ├── core/
│   │   │   ├── data_collector.py  # 데이터 수집 로직
│   │   │   └── api_client.py      # HTTP 클라이언트
│   │   └── config/
│   │       └── settings.py        # 환경 설정 (pydantic-settings)
│   ├── resources/                 # 아이콘, 이미지 등
│   ├── tests/
│   ├── build/
│   │   └── client.spec            # PyInstaller 빌드 스펙
│   └── requirements.txt
│
├── server/                        # FastAPI 백엔드
│   ├── app/
│   │   ├── main.py                # FastAPI 앱 생성 및 미들웨어
│   │   ├── api/v1/
│   │   │   ├── router.py          # 라우터 통합
│   │   │   └── endpoints/
│   │   │       ├── data.py        # 데이터 수신 엔드포인트
│   │   │       └── dashboard.py   # 대시보드 엔드포인트
│   │   ├── core/
│   │   │   ├── config.py          # 서버 설정
│   │   │   └── security.py        # 인증/보안 (추후 구현)
│   │   ├── db/
│   │   │   ├── base.py            # SQLAlchemy Base, Engine
│   │   │   └── session.py         # DB 세션 의존성
│   │   ├── models/
│   │   │   └── data.py            # ORM 모델 (RawData, NormalizedData)
│   │   ├── schemas/
│   │   │   └── data.py            # Pydantic 스키마
│   │   ├── services/
│   │   │   ├── data_service.py    # 비즈니스 로직
│   │   │   └── normalizer.py      # 정규화 로직
│   │   └── crud/
│   │       └── data.py            # DB CRUD
│   ├── alembic/                   # DB 마이그레이션
│   │   ├── env.py
│   │   └── versions/
│   ├── tests/
│   ├── requirements.txt
│   └── .env.example
│
├── web/                           # 웹 대시보드
│   ├── templates/
│   │   ├── dashboard/
│   │   │   └── index.html
│   │   └── components/            # 재사용 HTML 컴포넌트
│   └── static/
│       ├── css/dashboard.css
│       └── js/dashboard.js
│
├── db/                            # DB 스키마 및 시드 데이터
│   ├── schema.sql                 # 초기 테이블 DDL
│   ├── migrations/                # 수동 마이그레이션 SQL
│   └── seeds/
│       └── sample_data.sql        # 개발용 샘플 데이터
│
├── docs/
│   └── architecture.md            # 본 문서
│
├── docker/
│   ├── docker-compose.yml         # MariaDB + Server 통합 실행
│   └── server.Dockerfile
│
└── README.md
```

---

## 기술 스택 요약

| 영역 | 기술 |
|------|------|
| GUI 클라이언트 | Python 3.12, PyQt6, httpx, PyInstaller |
| API 서버 | Python 3.12, FastAPI, Uvicorn, SQLAlchemy, Alembic |
| DB | MariaDB 11, PyMySQL |
| 웹 대시보드 | HTML / CSS / Vanilla JS (또는 SPA 프레임워크로 교체 가능) |
| 인프라 | Docker, Docker Compose |

---

## 개발 시작 가이드

### 서버 실행

```bash
cd server
cp .env.example .env   # DB 정보 입력
pip install -r requirements.txt
alembic upgrade head   # DB 마이그레이션
uvicorn app.main:app --reload
```

### 클라이언트 실행

```bash
cd client
pip install -r requirements.txt
python app/main.py
```

### Docker로 MariaDB + Server 실행

```bash
cd docker
docker compose up -d
```

### 클라이언트 exe 빌드

```bash
cd client
pyinstaller build/client.spec
```
