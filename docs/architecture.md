# MLCC 계측기 데이터 수집 시스템 – 아키텍처

## 시스템 개요

GPIB 프로토콜로 계측기와 통신하는 클라이언트 PC에서 MLCC 특성(정전용량, 손실계수, ESR, 임피던스 등)을 측정하고,
FastAPI 서버를 경유하여 MariaDB에 저장한 뒤 웹 대시보드로 조회하는 시스템.

```
┌──────────────────────────────────────────────┐       HTTP/REST        ┌──────────────────────────────┐
│  Client (계측기 연결 PC)                       │ ─────────────────────▶ │  Server (Linux, FastAPI)     │
│                                              │  Authorization:        │                              │
│  ┌──────────────────────────────────────┐    │  Bearer <JWT>          │  ┌──────────────────────────┐ │
│  │  LoginDialog → JWT 획득               │    │                        │  │  API Router              │ │
│  └──────────────────────────────────────┘    │  POST /auth/login      │  │  /auth/login             │ │
│                 ↓                            │  POST /measurements    │  │  /measurements           │ │
│  ┌──────────────────────────────────────┐    │                        │  │  /instruments            │ │
│  │  MainWindow (QStackedWidget)         │    │                        │  │  /dashboard              │ │
│  │  ├── HomePage (카드 그리드)            │    │                        │  └────────────┬─────────────┘ │
│  │  ├── DCBiasMeasurementPage (전용)     │    │                        │               │               │
│  │  └── MeasurementPage (일반)           │    │                        │  ┌────────────▼─────────────┐ │
│  └──────────┬───────────────────────────┘    │                        │  │  MeasurementService      │ │
│             │ QThread                        │                        │  │  Normalizer (단위 변환)   │ │
│  ┌──────────▼───────────────────────────┐    │                        │  └────────────┬─────────────┘ │
│  │  MeasurementEngine                   │    │                        │               │               │
│  │  InstrumentRegistry                  │    │                        │  ┌────────────▼─────────────┐ │
│  └──────────┬───────────────────────────┘    │                        │  │  CRUD (SQLAlchemy)       │ │
│             │                               │                        │  └────────────┬─────────────┘ │
│  ┌──────────▼───────────────────────────┐    │                        └───────────────┼───────────────┘
│  │  Instrument Drivers                  │    │                                        │
│  │  (E4980A LCR, B2901A DC Source, …)  │    │                                        ▼
│  └──────────┬───────────────────────────┘    │                        ┌──────────────────────────────┐
│             │ PyVISA / GPIB                  │                        │  MariaDB (리눅스 서버 기설치) │
└─────────────┼──────────────────────────────┘                         │  users                       │
              ▼                                                         │  instruments                 │
  ┌────────────────────────┐                                            │  measurement_sessions        │
  │  계측기 (GPIB)          │                     브라우저 접속          │  raw_measurements            │
  │  E4980A LCR Meter       │       ┌──────────────────────┐            │  mlcc_measurements           │
  │  B2901A DC Source       │       │  Web Dashboard        │            └──────────────────────────────┘
  └────────────────────────┘       │  GET / (Jinja2)       │                        ▲
                                   └──────────────────────┘ ────────────────────────┘
                                                              GET /api/v1/dashboard
```

---

## 컴포넌트별 설명

### 1. Client (계측기 연결 PC, PyQt6)

| 항목 | 내용 |
|------|------|
| 언어/프레임워크 | Python 3.11+ + PyQt6 |
| 배포 형태 | 가상환경(`client/.venv`) 또는 PyInstaller `.exe` |
| GPIB 통신 | PyVISA (NI-VISA 또는 pyvisa-py 백엔드) |
| 인증 | JWT — `LoginDialog`에서 서버로부터 수신, `APIClient`가 헤더에 포함 |
| UI 테마 | Clean Light (`#F4F6F9` 배경, `#1E3A5F` 헤더, `#2563EB` 강조) |

#### 화면 흐름

```
main.py
  └→ LoginDialog                         POST /api/v1/auth/login
       username + password 입력            → { access_token, username }
            ↓ 성공
       MainWindow
         헤더  : 타이틀 | 계측기 연결 | 사용자명 + 로그아웃
         상태바: ● 서버 상태  ● GPIB 상태  세션명
         QStackedWidget
           [0] HomePage
                카드 그리드 (3×2)
                  정전용량 / ESR / Q Factor
                  임피던스 / DC Bias / 온도 특성
                      │ 클릭
                      ▼
           [1] DCBiasMeasurementPage    ← DC Bias 카드 전용
           [2+] MeasurementPage         ← 나머지 카드 (항목별 생성)
                      │ 뒤로가기
                      ▼
                HomePage 복귀
```

#### 패키지 구조

```
client/app/
├── main.py                        # LoginDialog → jwt → MainWindow 순서로 실행
├── config/
│   └── settings.py                # api_base_url, api_timeout, operator(로그인 후 설정)
├── core/
│   ├── api_client.py              # httpx 클라이언트: login(), set_token(), send_measurements()
│   │                              # 모든 요청에 Authorization: Bearer <JWT> 헤더 포함
│   └── measurement_engine.py      # 드라이버 로드 → 측정 → 서버 전송 조율
├── instruments/
│   ├── base.py                    # BaseInstrument(ABC), MeasurementResult, Characteristic, InstrumentType
│   ├── registry.py                # InstrumentRegistry – @InstrumentRegistry.register("E4980A")
│   ├── gpib/
│   │   └── connection.py          # GPIBConnectionManager (pyvisa.ResourceManager 래핑)
│   └── drivers/
│       ├── lcr_meter/
│       │   ├── base_lcr.py        # BaseLCRMeter: set_frequency/ac_level/dc_bias, disable_dc_bias
│       │   └── e4980a.py          # Keysight E4980A — CPD 모드, BIAS:STATe, INIT:CONT ON
│       └── dc_source/
│           └── b2901a.py          # Keysight B2901A DC Source
└── ui/
    ├── login_dialog.py            # QDialog: username + password, 인라인 오류 표시
    ├── main_window.py             # QMainWindow: 헤더 + QStackedWidget + 상태바(15초 서버 폴링)
    ├── styles/
    │   └── clean_light.qss        # 전체 앱 QSS 스타일시트 (Clean Light 테마)
    ├── pages/
    │   ├── home_page.py           # HomePage: 측정 항목 카드 그리드 (3×2)
    │   ├── measurement_page.py    # MeasurementPage: 조건 패널 + 실시간값 + 이력 테이블 (QThread)
    │   └── dc_bias_page.py        # DCBiasMeasurementPage: 전압 스윕 전용 (QThread + CSV 내보내기)
    ├── widgets/
    │   └── measurement_card.py    # QPushButton 기반 클릭 가능 카드 위젯
    └── dialogs/
        └── instrument_config.py   # 계측기 GPIB 연결 설정 다이얼로그
```

#### 새 드라이버 추가 방법

```python
# client/app/instruments/drivers/lcr_meter/new_model.py
from app.instruments.registry import InstrumentRegistry
from app.instruments.drivers.lcr_meter.base_lcr import BaseLCRMeter

@InstrumentRegistry.register("NEW_MODEL")
class NewModel(BaseLCRMeter):
    def connect(self): ...
    def disconnect(self): ...
    def identify(self) -> str: ...
    def configure(self, frequency, ac_level, dc_bias, **kwargs): ...
    def measure(self, **kwargs) -> list: ...
    def set_dc_bias(self, bias: float): ...
    def disable_dc_bias(self): ...    # DC Bias 스윕 후 DUT 보호 필수
```

#### E4980A GPIB SCPI 커맨드 명세

| 메서드 | 전송 커맨드 | 설명 |
|--------|------------|------|
| `configure()` | `:FUNC:IMP:TYPE CPD` | 측정 함수: Cp–D 모드 (MLCC 표준) |
| | `:FREQ <Hz>` | 측정 주파수 (20 Hz – 2 MHz) |
| | `:VOLT <Vrms>` | AC 신호 레벨 (5 mV – 2 V) |
| | `:BIAS:VOLT <V>` | DC 바이어스 전압 (0 – ±40 V) |
| | `:BIAS:STATe ON` | DC 바이어스 출력 활성화 |
| | `:INIT:CONT ON` | 연속 측정 모드 활성화 (FETC? 보장) |
| `measure()` | `:FETC?` | 최신 측정값 읽기 → `Cp(F), D(무차원)` |
| `set_dc_bias()` | `:BIAS:VOLT <V>` | DC 바이어스 전압만 변경 |
| `disable_dc_bias()` | `:BIAS:VOLT 0` | 전압 0V 복귀 |
| | `:BIAS:STATe OFF` | DC 바이어스 출력 차단 (DUT 보호) |

> **CPD vs CPRP**: `CPRP` 모드의 두 번째 반환값은 Rp(병렬저항)이며 ESR(직렬저항 Rs)과 다름.
> MLCC DC Bias 특성 평가(IEC 60384, JIS C 5101) 표준은 `CPD`(Cp + 손실계수 D)를 사용.

#### DC Bias 전압 스윕 흐름

```
[측정 시작] 클릭
    │
    ▼
configure()                ← FUNC:IMP:TYPE CPD, FREQ, VOLT, BIAS:VOLT 0, BIAS:STATe ON, INIT:CONT ON
    │
    ▼ (QThread)
for voltage in [0, 1, 2, …, 5]:
    set_dc_bias(voltage)   ← :BIAS:VOLT <V>
    sleep(delay_ms)        ← 측정 버퍼 갱신 대기 (≥ 1 측정 주기)
    measure()              ← :FETC? → Cp(F), D
    → 테이블 해당 행에 Cp 값 기입
    │
    ▼ (finally 블록, 정상/중지/예외 공통)
disable_dc_bias()          ← :BIAS:VOLT 0, :BIAS:STATe OFF (DUT 보호)
```

---

### 2. Server (Linux, FastAPI + Uvicorn)

| 항목 | 내용 |
|------|------|
| 언어/프레임워크 | Python 3.11+ + FastAPI + Uvicorn |
| 인증 | JWT (python-jose + passlib/bcrypt), 8시간 만료 |
| DB ORM | SQLAlchemy 2.x + PyMySQL |
| 마이그레이션 | Alembic |
| 웹 대시보드 | FastAPI StaticFiles + Jinja2Templates |
| 런타임 | Python 가상환경 (`.venv`) + systemd 서비스 |

#### 계층 구조

```
server/app/
├── main.py                    # FastAPI 앱, CORS, StaticFiles/Jinja2 마운트
├── api/v1/
│   ├── router.py
│   └── endpoints/
│       ├── auth.py            # POST /auth/login → JWT 발급 (DB User 또는 .env 관리자)
│       ├── measurements.py    # POST /measurements
│       ├── instruments.py     # GET/POST /instruments
│       └── dashboard.py       # GET /dashboard/summary|records
├── core/
│   ├── config.py              # DB, CORS, JWT 설정 (SECRET_KEY, ALGORITHM, EXPIRE_MINUTES)
│   └── security.py            # create_access_token, verify_token, hash_password, verify_password
├── services/
│   ├── measurement_service.py # 세션·계측기 자동 등록, 측정값 저장
│   └── normalizer.py          # MLCC 특성값 단위 정규화
├── crud/
│   ├── instrument.py
│   └── measurement.py
├── models/
│   ├── user.py                # User ORM (id, username, password_hash)
│   ├── instrument.py          # Instrument ORM
│   └── measurement.py         # MeasurementSession, RawMeasurement, MlccMeasurement ORM
├── schemas/
│   ├── auth.py                # LoginRequest, TokenResponse
│   ├── instrument.py
│   └── measurement.py
└── db/
    ├── base.py                # SQLAlchemy engine + Base + 모든 모델 import (Alembic용)
    └── session.py
```

#### 주요 API 엔드포인트

| Method | Path | 인증 | 설명 |
|--------|------|------|------|
| POST | `/api/v1/auth/login` | 불필요 | 로그인 → JWT 발급 |
| POST | `/api/v1/measurements` | JWT | MLCC 측정 데이터 수신·저장 |
| GET  | `/api/v1/instruments` | JWT | 등록된 계측기 목록 |
| POST | `/api/v1/instruments` | JWT | 계측기 수동 등록 |
| GET  | `/api/v1/dashboard/summary` | 불필요 | 요약 통계 |
| GET  | `/api/v1/dashboard/records` | 불필요 | 측정값 페이지네이션 |
| GET  | `/` | 불필요 | 웹 대시보드 (Jinja2) |

#### 인증 흐름

```
클라이언트 POST /auth/login { username, password }
    │
    ▼
DB users 테이블 조회 → 없으면 .env ADMIN_USERNAME/ADMIN_PASSWORD_HASH 비교
    │ bcrypt verify_password()
    ▼
JWT 생성 (HS256, 8시간 만료)
    → { access_token, token_type: "bearer", username }
```

---

### 3. Database (MariaDB – 리눅스 서버 기설치)

| 항목 | 내용 |
|------|------|
| DBMS | MariaDB (서버에 기설치, Docker 미사용) |
| 접속 드라이버 | PyMySQL |
| 스키마 파일 | `db/schema.sql` |
| 마이그레이션 | Alembic (`server/alembic/`) |

#### 테이블 구조

```
users
├── id, username (UNIQUE)
└── password_hash                       ← bcrypt 해시

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
└── raw_response TEXT, measured_at      ← GPIB 원시 응답 보존

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
│   │   ├── main.py                        # LoginDialog → MainWindow 실행 흐름
│   │   ├── config/settings.py             # api_base_url, api_timeout, operator
│   │   ├── core/
│   │   │   ├── measurement_engine.py
│   │   │   └── api_client.py              # JWT 포함 HTTP 클라이언트
│   │   ├── instruments/
│   │   │   ├── base.py
│   │   │   ├── registry.py
│   │   │   ├── gpib/connection.py
│   │   │   └── drivers/
│   │   │       ├── lcr_meter/base_lcr.py  # disable_dc_bias() 추가
│   │   │       ├── lcr_meter/e4980a.py    # CPD 모드, BIAS:STATe, INIT:CONT ON
│   │   │       └── dc_source/b2901a.py
│   │   └── ui/
│   │       ├── login_dialog.py            # QDialog: 로그인 폼
│   │       ├── main_window.py             # 헤더 + QStackedWidget + 상태바
│   │       ├── styles/
│   │       │   └── clean_light.qss        # Clean Light QSS 테마
│   │       ├── pages/
│   │       │   ├── home_page.py           # 측정 항목 카드 그리드 (3×2)
│   │       │   ├── measurement_page.py    # 일반 측정 페이지 (QThread)
│   │       │   └── dc_bias_page.py        # DC Bias 전압 스윕 전용 페이지 (QThread + CSV)
│   │       ├── widgets/
│   │       │   └── measurement_card.py    # 클릭 가능 카드 위젯
│   │       └── dialogs/
│   │           └── instrument_config.py   # 계측기 GPIB 연결 설정
│   ├── .venv/
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
│   │   │       ├── auth.py                # POST /auth/login (JWT 발급)
│   │   │       ├── measurements.py
│   │   │       ├── instruments.py
│   │   │       └── dashboard.py
│   │   ├── core/
│   │   │   ├── config.py                  # DB + JWT 설정
│   │   │   └── security.py                # JWT 생성/검증, bcrypt 해싱
│   │   ├── db/
│   │   ├── models/
│   │   │   ├── user.py                    # User ORM (신규)
│   │   │   ├── instrument.py
│   │   │   └── measurement.py
│   │   ├── schemas/
│   │   │   ├── auth.py                    # LoginRequest, TokenResponse (신규)
│   │   │   ├── instrument.py
│   │   │   └── measurement.py
│   │   ├── services/
│   │   │   ├── measurement_service.py
│   │   │   └── normalizer.py
│   │   └── crud/
│   ├── alembic/
│   ├── deploy/
│   │   └── dc-server.service
│   ├── tests/
│   ├── requirements.txt                   # python-jose, passlib[bcrypt] 추가
│   └── .env.example
│
├── web/
│   ├── templates/dashboard/index.html
│   └── static/
│       ├── css/dashboard.css
│       └── js/dashboard.js
│
├── db/
│   ├── schema.sql
│   └── seeds/sample_data.sql
│
├── scripts/
│   ├── setup_server.sh
│   ├── start_server.sh
│   └── setup_client.sh
│
├── docs/architecture.md
├── README.md
└── CLAUDE.md
```

---

## 기술 스택 요약

| 영역 | 기술 |
|------|------|
| GUI 클라이언트 | Python 3.11+, PyQt6, PyVISA, httpx, PyInstaller |
| GPIB 통신 | PyVISA + NI-VISA 또는 pyvisa-py |
| 인증 | JWT / HS256 (python-jose + passlib/bcrypt) |
| API 서버 | Python 3.11+, FastAPI, Uvicorn, SQLAlchemy 2.x, Alembic, Jinja2 |
| DB | MariaDB, PyMySQL |
| 웹 대시보드 | Jinja2 (서버사이드) + Vanilla JS |
| 인프라 | Python venv, systemd (Docker 미사용) |
