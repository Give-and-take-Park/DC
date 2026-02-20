# DC – MLCC 계측기 데이터 수집 시스템

GPIB 계측기로 MLCC 특성(용량, ESR, DF, 임피던스 등)을 측정하고,
FastAPI 서버를 통해 MariaDB에 저장한 뒤 웹 대시보드로 조회하는 시스템.

> **인프라**: Docker 미사용. Python 가상환경(venv) + systemd으로 운영합니다.
> MariaDB는 리눅스 서버에 기설치된 것을 사용합니다.

---

## 기술 스택

| 영역 | 기술 |
|------|------|
| GUI 클라이언트 | Python 3.11+, PyQt6, PyVISA → `.exe` (PyInstaller) |
| GPIB 통신 | PyVISA + NI-VISA 또는 pyvisa-py |
| API 서버 | Python 3.11+, FastAPI, Uvicorn, SQLAlchemy, Alembic |
| DB | MariaDB (서버 기설치), PyMySQL |
| 웹 대시보드 | FastAPI + Jinja2 (Python 일원화) |
| 인프라 | Python venv, systemd |

---

## 빠른 시작

### 1. 서버 환경 설정

```bash
# 가상환경 생성 및 의존성 설치
bash scripts/setup_server.sh

# .env 파일에 DB 접속 정보 입력
vi server/.env

# DB 스키마 초기화 (최초 1회)
# 방법 A: 직접 SQL 실행
mysql -u dc_user -p dc_db < db/schema.sql

# 방법 B: Alembic 마이그레이션
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

# 클라이언트 실행
client/.venv/bin/python client/app/main.py
```

> **GPIB 드라이버 필요**: GPIB 통신에는 NI-VISA 또는 pyvisa-py 백엔드가 필요합니다.
> - NI-VISA (권장): Keysight/NI 사이트에서 설치
> - pyvisa-py (무료, USB-GPIB 어댑터 필요): `pip install pyvisa-py` 로 설치됨

### 3. 개발용 샘플 데이터 투입

```bash
mysql -u dc_user -p dc_db < db/seeds/sample_data.sql
```

---

## 리눅스 서버 배포 (systemd)

```bash
# 프로젝트를 /opt/dc 에 배포
sudo cp -r . /opt/dc
sudo chown -R dc:dc /opt/dc

# 가상환경 설치
sudo -u dc bash /opt/dc/scripts/setup_server.sh
sudo -u dc vi /opt/dc/server/.env  # DB 접속 정보 입력

# systemd 서비스 등록
sudo cp /opt/dc/server/deploy/dc-server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now dc-server

# 상태 확인
sudo systemctl status dc-server
sudo journalctl -u dc-server -f
```

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
    def configure(self, **kwargs): ...
    def measure(self, **kwargs) -> list[MeasurementResult]: ...
```

등록 후 GUI의 계측기 모델 목록에 자동으로 나타납니다.

---

## 문서

- [아키텍처 상세 설명](docs/architecture.md)

---

## 프로젝트 구조

```
DC/
├── client/      # PyQt6 GUI 클라이언트 + PyVISA 드라이버
├── server/      # FastAPI 백엔드 서버
├── web/         # 웹 대시보드 (Jinja2 + 정적 파일)
├── db/          # DB 스키마(MLCC DDL) 및 시드 데이터
├── scripts/     # venv 설정·실행 스크립트
└── docs/        # 아키텍처 문서
```
