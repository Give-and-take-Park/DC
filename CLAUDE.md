# CLAUDE.md

MLCC 계측기 데이터 수집 시스템. Python venv + systemd 기반 (Docker 미사용).

## 개발 명령어

### 서버
```bash
bash scripts/setup_server.sh          # 초기 설정 (venv 생성, 패키지 설치)
bash scripts/start_server.sh          # uvicorn --reload, :8000
```

### 클라이언트
```bash
bash scripts/setup_client.sh          # 초기 설정
client/.venv/bin/python client/app/main.py  # 실행
```

### DB
```bash
# 스키마 초기화 (SQL 직접)
mysql -u dc_user -p dc_db < db/schema.sql

# 마이그레이션
cd server && ../.venv/bin/alembic upgrade head
cd server && ../.venv/bin/alembic revision --autogenerate -m "설명"

# 샘플 데이터
mysql -u dc_user -p dc_db < db/seeds/sample_data.sql
```

### 빌드
```bash
cd client && .venv/bin/pyinstaller build/client.spec  # exe 빌드
```

## 아키텍처

```
[클라이언트]
PyQt6 GUI → MeasurementEngine → InstrumentRegistry → Driver → GPIB 계측기
                                                                    ↓
                                                               APIClient → Server

[서버]
endpoint → MeasurementService → CRUD → SQLAlchemy → MariaDB
GET /  → Jinja2 웹 대시보드 (FastAPI 직접 서빙)
```

- **단위 정규화**: `server/app/services/normalizer.py`에서 수신값을 표준 단위(F, Ω, V)로 변환 후 저장

## 계측기 드라이버 추가

1. `client/app/instruments/drivers/{type}/{model}.py` 생성
2. `@InstrumentRegistry.register("MODEL_NAME")` 데코레이터 적용
3. `BaseLCRMeter` 또는 `BaseInstrument`의 추상 메서드 구현
4. 등록 시 GUI 계측기 목록에 자동 반영

## API 페이로드

`POST /api/v1/measurements` — `MeasurementSessionCreate`

```json
{
  "client_id": "string",
  "session_name": "string (optional)",
  "operator": "string (optional)",
  "instrument": {
    "model": "string",
    "gpib_address": 0,
    "type": "string"
  },
  "measurements": [
    {
      "characteristic": "CharacteristicType",
      "value": 0.0,
      "unit": "string",
      "frequency": 0.0,
      "dc_bias": 0.0,
      "temperature": 0.0,
      "raw_response": "string"
    }
  ]
}
```

## 환경 변수

`server/.env`
```
DB_HOST=
DB_PORT=
DB_NAME=
DB_USER=
DB_PASSWORD=
CORS_ORIGINS=
```

`client/.env`
```
API_BASE_URL=
API_TIMEOUT=
```
