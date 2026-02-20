# MLCC 계측기 데이터 수집 시스템 – 아키텍처

## 시스템 개요

GPIB 프로토콜로 계측기와 통신하는 클라이언트 PC에서 MLCC 특성(용량, ESR, DF, 임피던스 등)을 측정하고,
FastAPI 서버를 경유하여 MariaDB에 저장한 뒤 웹 대시보드로 조회하는 시스템.

```
┌──────────────────────────────────────────┐       HTTP/REST        ┌──────────────────────────────┐
│  Client (계측기 연결 PC)                   │ ─────────────────────▶ │  Server (Linux, FastAPI)     │
│                                          │  POST /api/v1/         │                              │
│  ┌──────────────────────────────────┐    │  measurements          │  ┌──────────────────────────┐ │
│  │  PyQt6 GUI                       │    │                        │  │  API Router              │ │
│  │  ┌──────────────────────────┐    │    │                        │  │  /measurements           │ │
│  │  │  MeasurementEngine       │    │    │                        │  │  /instruments            │ │
│  │  │  InstrumentRegistry      │    │    │                        │  │  /dashboard              │ │
│  │  └──────────┬───────────────┘    │    │                        │  └────────────┬─────────────┘ │
│  │             │                    │    │                        │               │               │
│  │  ┌──────────▼───────────────┐    │    │                        │  ┌────────────▼─────────────┐ │
│  │  │  Instrument Drivers      │    │    │                        │  │  MeasurementService      │ │
│  │  │  (E4980A, B2901A, …)    │    │    │                        │  │  Normalizer (단위 변환)   │ │
│  │  └──────────┬───────────────┘    │    │                        │  └────────────┬─────────────┘ │
│  │             │ PyVISA/GPIB        │    │                        │               │               │
│  └─────────────┼────────────────────┘    │                        │  ┌────────────▼─────────────┐ │
│                │                         │                        │  │  CRUD Layer (SQLAlchemy)  │ │
└────────────────┼─────────────────────────┘                        │  └────────────┬─────────────┘ │
                 │                                                   └───────────────┼───────────────┘
                 ▼                                                                   │
    ┌────────────────────────┐                                                       ▼
    │  계측기 (GPIB)          │                                       ┌──────────────────────────────┐
    │  E4980A LCR Meter       │                                       │  MariaDB (리눅스 서버 기설치) │
    │  B2901A DC Source       │                                       │                              │
    │  (기타 드라이버 추가 가능) │                                      │  instruments                 │
    └────────────────────────┘                                       │  measurement_sessions         │
                                                                     │  raw_measurements             │
                                              브라우저 접속           │  mlcc_measurements            │
                                    ┌──────────────────────┐         └──────────────────────────────┘
                                    │  Web Dashboard        │                      ▲
                                    │  GET / (Jinja2)       │ ─────────────────────┘
                                    │  HTML + CSS + JS      │  GET /api/v1/dashboard
                                    └──────────────────────┘
```

---

## 컴포넌트별 설명

### 1. Client (계측기 연결 PC, PyQt6)

| 항목 | 내용 |
|------|------|
| 언어/프레임워크 | Python 3.11+ + PyQt6 |
| 배포 형태 | 가상환경(`client/.venv`) 또는 PyInstaller `.exe` |
| GPIB 통신 | PyVISA (NI-VISA 또는 pyvisa-py 백엔드) |
| 주요 패턴 | Abstract Base + Registry (데코레이터 드라이버 등록) |

**패키지 구조**

```
client/app/
├── instruments/
│   ├── base.py            # BaseInstrument(ABC), MeasurementResult, Characteristic, InstrumentType
│   ├── registry.py        # InstrumentRegistry – @InstrumentRegistry.register("E4980A")
│   ├── gpib/
│   │   └── connection.py  # GPIBConnectionManager (pyvisa.ResourceManager 래핑)
│   └── drivers/
│       ├── lcr_meter/
│       │   ├── base_lcr.py   # BaseLCRMeter – LCR 공통 인터페이스
│       │   └── e4980a.py     # Keysight E4980A 드라이버
│       └── dc_source/
│           └── b2901a.py     # Keysight B2901A 드라이버
├── core/
│   ├── measurement_engine.py  # 드라이버 로드 → 측정 → 서버 전송 조율
│   └── api_client.py          # HTTP 클라이언트 (httpx)
├── ui/
│   ├── main_window.py
│   ├── widgets/
│   └── dialogs/
│       └── instrument_config.py  # 계측기 연결 설정 다이얼로그
└── config/settings.py
```

**새 드라이버 추가 방법**

```python
# client/app/instruments/drivers/lcr_meter/new_model.py
from app.instruments.registry import InstrumentRegistry
from app.instruments.drivers.lcr_meter.base_lcr import BaseLCRMeter

@InstrumentRegistry.register("NEW_MODEL")
class NewModel(BaseLCRMeter):
    def connect(self): ...
    def disconnect(self): ...
    def identify(self) -> str: ...
    def configure(self, **kwargs): ...
    def measure(self, **kwargs) -> list: ...
```

---

### 2. Server (Linux, FastAPI + Uvicorn)

| 항목 | 내용 |
|------|------|
| 언어/프레임워크 | Python 3.11+ + FastAPI + Uvicorn |
| DB ORM | SQLAlchemy 2.x + PyMySQL |
| 마이그레이션 | Alembic |
| 웹 대시보드 | FastAPI StaticFiles + Jinja2Templates |
| 런타임 | Python 가상환경 (`.venv`) + systemd 서비스 |

**계층 구조**

```
server/app/
├── main.py                  # FastAPI 앱, CORS, StaticFiles/Jinja2 마운트
├── api/v1/
│   ├── router.py
│   └── endpoints/
│       ├── measurements.py  # POST /measurements
│       ├── instruments.py   # GET/POST /instruments
│       └── dashboard.py     # GET /dashboard/summary|records
├── services/
│   ├── measurement_service.py  # 세션·계측기 자동 등록, 측정값 저장
│   └── normalizer.py           # MLCC 특성값 단위 정규화
├── crud/
│   ├── instrument.py
│   └── measurement.py
├── models/
│   ├── instrument.py        # Instrument ORM
│   └── measurement.py       # MeasurementSession, RawMeasurement, MlccMeasurement ORM
├── schemas/
│   ├── instrument.py
│   └── measurement.py
├── core/config.py
└── db/
    ├── base.py
    └── session.py
```

**주요 API 엔드포인트**

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/v1/measurements` | MLCC 측정 데이터 수신·저장 |
| GET  | `/api/v1/instruments` | 등록된 계측기 목록 |
| POST | `/api/v1/instruments` | 계측기 수동 등록 |
| GET  | `/api/v1/dashboard/summary` | 요약 통계 |
| GET  | `/api/v1/dashboard/records` | 측정값 페이지네이션 |
| GET  | `/` | 웹 대시보드 (Jinja2) |

---

### 3. Database (MariaDB – 리눅스 서버 기설치)

| 항목 | 내용 |
|------|------|
| DBMS | MariaDB (서버에 기설치, Docker 미사용) |
| 접속 드라이버 | PyMySQL |
| 스키마 파일 | `db/schema.sql` |
| 마이그레이션 | Alembic (`server/alembic/`) |

**테이블 구조**

```
instruments
├── id, name, model, manufacturer
├── instrument_type  ENUM(lcr_meter|dc_source|oscilloscope|multimeter)
└── gpib_address, description

measurement_sessions
├── id, client_id, session_name
├── started_at, ended_at
└── operator, notes

raw_measurements
├── id, session_id→, instrument_id→
└── raw_response TEXT, measured_at          ← GPIB 원시 응답 보존

mlcc_measurements
├── id, raw_measurement_id→, session_id→, instrument_id→
├── characteristic  ENUM(capacitance|esr|df|impedance|q_factor|dc_bias)
├── value DOUBLE, unit VARCHAR(20)
├── frequency DOUBLE (Hz)
├── dc_bias DOUBLE (V)
└── temperature DOUBLE (°C), measured_at
```

---

### 4. 인프라 (Python 가상환경 + systemd)

Docker를 사용하지 않으며, 모든 컴포넌트는 Python 가상환경에서 실행됩니다.

| 컴포넌트 | 런타임 |
|---------|--------|
| 서버 | `.venv/bin/uvicorn` + systemd (`server/deploy/dc-server.service`) |
| 클라이언트 | `client/.venv/bin/python` 또는 PyInstaller exe |
| MariaDB | 리눅스 서버 기설치 (OS 패키지 관리) |

---

## 프로젝트 폴더 구조

```
DC/
├── client/
│   ├── app/
│   │   ├── main.py
│   │   ├── config/settings.py
│   │   ├── core/
│   │   │   ├── measurement_engine.py
│   │   │   └── api_client.py
│   │   ├── instruments/
│   │   │   ├── base.py
│   │   │   ├── registry.py
│   │   │   ├── gpib/connection.py
│   │   │   └── drivers/
│   │   │       ├── lcr_meter/base_lcr.py
│   │   │       ├── lcr_meter/e4980a.py
│   │   │       └── dc_source/b2901a.py
│   │   └── ui/
│   │       ├── main_window.py
│   │       ├── widgets/
│   │       └── dialogs/instrument_config.py
│   ├── .venv/                  ← 클라이언트 전용 가상환경 (git 제외)
│   ├── resources/
│   ├── tests/
│   └── requirements.txt
│
├── server/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/v1/
│   │   │   ├── router.py
│   │   │   └── endpoints/
│   │   │       ├── measurements.py
│   │   │       ├── instruments.py
│   │   │       └── dashboard.py
│   │   ├── core/config.py
│   │   ├── db/
│   │   ├── models/
│   │   │   ├── instrument.py
│   │   │   └── measurement.py
│   │   ├── schemas/
│   │   ├── services/
│   │   │   ├── measurement_service.py
│   │   │   └── normalizer.py
│   │   └── crud/
│   ├── alembic/
│   ├── alembic.ini
│   ├── deploy/
│   │   └── dc-server.service   ← systemd 유닛 파일
│   ├── tests/
│   ├── requirements.txt
│   └── .env.example
│
├── web/
│   ├── templates/dashboard/index.html
│   └── static/
│       ├── css/dashboard.css
│       └── js/dashboard.js
│
├── db/
│   ├── schema.sql              ← MLCC DDL
│   └── seeds/sample_data.sql
│
├── scripts/
│   ├── setup_server.sh         ← 서버 가상환경 초기 설정
│   ├── start_server.sh         ← 서버 실행
│   └── setup_client.sh         ← 클라이언트 가상환경 초기 설정
│
├── .venv/                      ← 서버 공용 가상환경 (git 제외)
├── docs/architecture.md
└── README.md
```

---

## 기술 스택 요약

| 영역 | 기술 |
|------|------|
| GUI 클라이언트 | Python 3.11+, PyQt6, PyVISA, httpx, PyInstaller |
| GPIB 통신 | PyVISA + NI-VISA 또는 pyvisa-py |
| API 서버 | Python 3.11+, FastAPI, Uvicorn, SQLAlchemy 2.x, Alembic, Jinja2 |
| DB | MariaDB, PyMySQL |
| 웹 대시보드 | Jinja2 (서버사이드) + Vanilla JS |
| 인프라 | Python venv, systemd (Docker 미사용) |
