# RIMS – Raffaello Inspection & Metrology System

GPIB 계측기로 MLCC 특성(정전용량, 손실계수, ESR, 임피던스 등)을 측정하거나
광학 설계분석 이미지를 서버에 업로드·분석하고 결과 Excel을 다운로드하며,
FastAPI 서버를 통해 MariaDB에 저장한 뒤 웹 대시보드로 조회하는 시스템.

> **인프라**: Docker 미사용. Python 가상환경(venv) + systemd으로 운영합니다.
> MariaDB는 리눅스 서버에 기설치된 것을 사용합니다.

---

## 기술 스택

| 영역 | 기술 |
|------|------|
| GUI 클라이언트 | Python 3.11+, PyQt6, PyVISA → `RIMS.exe` (PyInstaller) |
| GPIB 통신 | PyVISA + NI-VISA 또는 pyvisa-py |
| API 서버 | Python 3.11+, FastAPI, Uvicorn, SQLAlchemy, Alembic |
| 인증 | Knox ID 단독 입력 (접속 로그 서버 전송) |
| DB | MariaDB (서버 기설치), PyMySQL |
| 광학 분석 결과 | openpyxl (Excel 생성) |
| 웹 대시보드 | FastAPI + Jinja2 (Python 일원화) |
| 인프라 | Python venv, systemd |

---

## 빠른 시작

### 1. 서버 환경 설정

```bash
# 가상환경 생성 및 의존성 설치
bash scripts/setup_server.sh

# .env 파일에 DB 접속 정보 및 JWT 설정 입력
vi server/.env
```

`server/.env` 필수 항목:
```
DB_HOST=localhost
DB_PORT=3306
DB_NAME=dc_db
DB_USER=dc_user
DB_PASSWORD=your_db_password

SECRET_KEY=your-secret-key-change-in-production
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=        # 아래 명령어로 생성
```

초기 관리자 비밀번호 해시 생성:
```bash
cd server && ../.venv/bin/python -c \
  "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('원하는비밀번호'))"
```

```bash
# DB 스키마 초기화 (최초 1회)
# 방법 A: 직접 SQL 실행
mysql -u dc_user -p dc_db < db/schema.sql

# 방법 B: Alembic 마이그레이션 (User 테이블 포함)
cd server && ../.venv/bin/alembic upgrade head && cd ..

# 서버 실행 (개발, --reload 포함)
bash scripts/start_server.sh
```

서버 기동 후 브라우저에서 `http://localhost:8000` 으로 대시보드에 접속합니다.
API 문서: `http://localhost:8000/docs`

### 2. 클라이언트 환경 설정

```bash
# 가상환경 생성 및 의존성 설치
bash scripts/setup_client.sh

# 클라이언트 실행 (Knox ID 입력 다이얼로그가 먼저 표시됨)
client/.venv/bin/python client/app/main.py
```

> **GPIB 드라이버 필요**: GPIB 통신에는 NI-VISA 또는 pyvisa-py 백엔드가 필요합니다.
> - NI-VISA (권장): Keysight/NI 사이트에서 설치
> - pyvisa-py (무료, USB-GPIB 어댑터 필요): `pip install pyvisa-py` 로 설치됨

### 3. 클라이언트 exe 빌드 (Windows)

**전제 조건**: 클라이언트 가상환경이 이미 설정되어 있어야 합니다 (`setup_client.sh` 실행 완료).

```bash
# client/ 디렉터리에서 실행
cd client
.venv/Scripts/pip install pyinstaller   # 최초 1회

.venv/Scripts/pyinstaller build/client.spec
```

빌드가 완료되면 `client/dist/RIMS.exe` 가 생성됩니다.

**빌드 후 배포 시 함께 배포할 파일:**
```
RIMS.exe
client/.env          ← API_BASE_URL, API_TIMEOUT 설정
```

`client/.env` 예시:
```
API_BASE_URL=http://<서버IP>:8000
API_TIMEOUT=30
```

### 4. 개발용 샘플 데이터 투입

```bash
mysql -u dc_user -p dc_db < db/seeds/sample_data.sql
```

---

## GUI 클라이언트 화면 구성

```
로그인 다이얼로그 (Knox ID 입력)
    └→ 메인 윈도우 (창 타이틀: RIMS)
         ├── 헤더: RIMS + Raffaello Inspection & Metrology System | 사용자명 + 홈으로 + 로그아웃
         ├── 홈 화면: 3종 모듈 카드
         │     ├── ⚡ DC-bias         → DC Bias 전압 스윕 전용 페이지
         │     ├── 🔧 HALT / 8585     → 신뢰성 측정 페이지 (GPIB)
         │     └── 🔬 광학 설계분석   → 이미지 업로드 페이지
         ├── DC Bias 측정 페이지 (전용)
         │     ├── 왼쪽(고정 300px): 계측기 연결 + 측정 모드·주파수·유지시간·LOT no. 설정
         │     └── 오른쪽: No. / Time(s) / Freq.(Hz) / AC(V) / DC(V) / CHIP Cp·DF 테이블
         │           + CSV 내보내기 / Enter로 다음 행 이동 / Delete·Backspace로 셀 삭제
         └── 일반 측정 페이지 (HALT·8585, 광학 설계분석)
               ├── 왼쪽(고정 260px): 계측기 연결 + 측정 조건
               └── 오른쪽: 실시간 측정값 + 이력 테이블 (범위 선택 + Ctrl+C 복사)
```

---

## 광학 설계분석 모듈

GPIB 계측기 없이 광학 이미지를 서버에 업로드하고, 분석 결과 Excel을 다운로드합니다.

### 클라이언트 파이프라인 (5단계, QThread 백그라운드 실행)

| 단계 | 동작 |
|------|------|
| 1 | 선택한 이미지를 ZIP으로 압축 |
| 2 | `POST /optical/upload` — ZIP 전송, `folder_name` 수신 |
| 3 | `POST /optical/analyze` — 서버 분석 완료까지 대기 (동기) |
| 4 | `GET /optical/result/{folder_name}` — Excel 파일 수신 |
| 5 | `~/Downloads/{folder_name}_result.xlsx` 저장 |

### 서버 파일 경로

| 경로 | 설명 |
|------|------|
| `{UPLOAD_DIR}/optical/uploads/{folder_name}/` | ZIP 압축 해제 이미지 (경로 A) |
| `{UPLOAD_DIR}/optical/results/{folder_name}/` | 분석 결과 Excel (경로 B) |

- `folder_name` 형식: `{lot_no}_{YYYYMMDD_HHMMSS}` (업로드·분석·다운로드 공통 키)
- 지원 이미지 형식: JPEG, PNG, BMP, TIFF, WebP / ZIP 최대 크기: 50 MB
- 분석 결과 Excel 헤더: No. / 파일명 / 분석 상태 (openpyxl 생성, `#1E3A5F` 헤더 스타일)

### API

```
POST /api/v1/optical/upload          → { folder_name, lot_no, operator, status }
POST /api/v1/optical/analyze         → { folder_name, status: "analyzed" }
GET  /api/v1/optical/result/{folder_name} → Excel 파일 직접 반환 (.xlsx)
```

---

## DC Bias 특성 측정 (E4980A)

DC Bias에 따른 정전용량 변화를 조건별로 수동 입력하거나 자동 수집합니다.

### 측정 결과 테이블 컬럼

| 컬럼 | 설명 |
|------|------|
| No. | 측정 행 번호 (자동) |
| Time(s) | 전압 인가 후 유지 시간 |
| Freq.(Hz) | 측정 주파수 |
| AC(V) | AC 신호 레벨 |
| DC(V) | 인가 DC 바이어스 전압 |
| CHIP n – Cp(nF) | n번째 CHIP 정전용량 |
| CHIP n – DF | n번째 CHIP 손실계수 |

- 측정 시작 시마다 CHIP 열이 자동 추가 (CHIP 1, CHIP 2, …)
- Enter: 다음 행으로 이동 (마지막 행에서 새 행 자동 추가)
- Delete / Backspace: 선택 셀 값 삭제
- Ctrl+C: 선택 범위 복사
- CSV 내보내기 지원

SCPI 측정 함수: `:FUNC:IMP:TYPE CPD` (Cp + 손실계수 D, MLCC 평가 표준)

---

## 계측기 드라이버 추가

새 계측기 드라이버는 `@InstrumentRegistry.register` 데코레이터로 등록합니다.

```python
# client/app/instruments/drivers/lcr_meter/new_model.py
from app.instruments.registry import InstrumentRegistry
from app.instruments.drivers.lcr_meter.base_lcr import BaseLCRMeter
from app.instruments.base import Characteristic, MeasurementResult

@InstrumentRegistry.register("NEW_MODEL")
class NewModel(BaseLCRMeter):
    def connect(self): ...
    def disconnect(self): ...
    def identify(self) -> str: ...
    def configure(self, frequency, ac_level, dc_bias, **kwargs): ...
    def measure(self, **kwargs) -> list[MeasurementResult]: ...
    def set_dc_bias(self, bias: float): ...
    def disable_dc_bias(self): ...   # DC Bias 스윕 후 DUT 보호용
```

등록 후 GUI의 계측기 모델 목록에 자동으로 나타납니다.

---

## 리눅스 서버 배포 (systemd)

```bash
# 프로젝트를 /opt/dc 에 배포
sudo cp -r . /opt/dc
sudo chown -R dc:dc /opt/dc

# 가상환경 설치
sudo -u dc bash /opt/dc/scripts/setup_server.sh
sudo -u dc vi /opt/dc/server/.env  # DB·JWT 설정 입력

# systemd 서비스 등록
sudo cp /opt/dc/server/deploy/dc-server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now dc-server

# 상태 확인
sudo systemctl status dc-server
sudo journalctl -u dc-server -f
```

---

## 문서

- [아키텍처 상세 설명](docs/architecture.md)

---

## 프로젝트 구조

```
DC/
├── client/      # PyQt6 GUI 클라이언트 (RIMS.exe) + PyVISA 드라이버
├── server/      # FastAPI 백엔드 서버
├── web/         # 웹 대시보드 (Jinja2 + 정적 파일)
├── db/          # DB 스키마 및 시드 데이터
├── scripts/     # venv 설정·실행 스크립트
└── docs/        # 아키텍처 문서
```
