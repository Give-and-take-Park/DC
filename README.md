# DC – MLCC 계측기 데이터 수집 시스템

GPIB 계측기로 MLCC 특성(정전용량, 손실계수, ESR, 임피던스 등)을 측정하거나
광학 설계분석 이미지를 업로드하고, FastAPI 서버를 통해 MariaDB에 저장한 뒤
웹 대시보드로 조회하는 시스템.

> **인프라**: Docker 미사용. Python 가상환경(venv) + systemd으로 운영합니다.
> MariaDB는 리눅스 서버에 기설치된 것을 사용합니다.

---

## 기술 스택

| 영역 | 기술 |
|------|------|
| GUI 클라이언트 | Python 3.11+, PyQt6, PyVISA → `.exe` (PyInstaller) |
| GPIB 통신 | PyVISA + NI-VISA 또는 pyvisa-py |
| API 서버 | Python 3.11+, FastAPI, Uvicorn, SQLAlchemy, Alembic |
| 인증 | JWT (python-jose + passlib/bcrypt) |
| DB | MariaDB (서버 기설치), PyMySQL |
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

# 클라이언트 실행 (로그인 다이얼로그가 먼저 표시됨)
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

빌드가 완료되면 `client/dist/DCClient.exe` 가 생성됩니다 (약 40 MB).

> **오프라인 데모 계정**: `ID: admin` / `PW: admin1111` 으로 로그인하면 서버 없이도 GUI 전체 기능을 확인할 수 있습니다.

**빌드 후 배포 시 함께 배포할 파일:**
```
DCClient.exe
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
로그인 다이얼로그
    └→ 메인 윈도우
         ├── 헤더: 앱 타이틀 | 사용자명 + 로그아웃
         ├── 홈 화면: 3종 모듈 카드
         │     ├── ⚡ DC-bias         → DC Bias 전압 스윕 전용 페이지
         │     ├── 🔧 HALT / 8585     → 신뢰성 측정 페이지 (GPIB)
         │     └── 🔬 광학 설계분석   → 이미지 업로드 페이지
         ├── DC Bias 측정 페이지 (전용)
         │     ├── 왼쪽(고정 300px): 계측기 연결 + 주파수·AC Level·전압 범위·스텝·지연 설정
         │     └── 오른쪽: 인가전압(V) × n차측정(F) 엑셀형 테이블 + CSV 내보내기
         └── 일반 측정 페이지 (HALT·8585, 광학 설계분석)
               ├── 왼쪽(고정 260px): 계측기 연결 + 측정 조건
               └── 오른쪽: 실시간 측정값 + 이력 테이블 (범위 선택 + Ctrl+C 복사)
```

---

## 광학 설계분석 모듈

GPIB 계측기 없이 사용자가 별도로 저장한 광학 이미지를 서버에 업로드합니다.

| 지원 형식 | 최대 크기 | 저장 위치 |
|-----------|----------|-----------|
| JPEG, PNG, BMP, TIFF, WebP | 50 MB | 서버 `{UPLOAD_DIR}/optical/` |

- 업로드 시 원본 파일명·작업자·세션명·설명을 함께 저장
- 서버에는 UUID 기반 파일명으로 저장 (원본 파일명 충돌 방지)
- 업로드 이력은 `GET /api/v1/optical/records` 로 조회

---

## DC Bias 특성 측정 (E4980A)

전압 스윕으로 DC Bias에 따른 정전용량 변화를 자동 수집합니다.

| 설정 항목 | 범위 | 기본값 |
|-----------|------|--------|
| 측정 주파수 | 20 Hz – 2 MHz | 1,000 Hz |
| AC 신호 레벨 | 5 mV – 2 V rms | 1.0 V |
| 시작 전압 | -40 – +40 V | 0.0 V |
| 종료 전압 | -40 – +40 V | 5.0 V |
| 전압 스텝 | 0.01 – 10 V | 1.0 V |
| 지연 시간 | 0 – 5,000 ms | 100 ms |

측정 결과는 **인가 전압(V) × n차 측정(F)** 형태의 테이블에 자동 기입되며,
"측정 시작"을 반복하면 열이 추가되어 여러 차수의 측정을 비교할 수 있습니다.
불필요한 측정 열은 **우클릭 컨텍스트 메뉴** 또는 **Delete 키**로 삭제할 수 있으며,
삭제 후 1차·2차·... 순으로 헤더가 자동 재정렬됩니다.

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
├── client/      # PyQt6 GUI 클라이언트 + PyVISA 드라이버
├── server/      # FastAPI 백엔드 서버 (JWT 인증 포함)
├── web/         # 웹 대시보드 (Jinja2 + 정적 파일)
├── db/          # DB 스키마(MLCC DDL) 및 시드 데이터
├── scripts/     # venv 설정·실행 스크립트
└── docs/        # 아키텍처 문서
```
