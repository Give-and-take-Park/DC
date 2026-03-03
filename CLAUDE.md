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
client/.venv/bin/python client/app/main.py  # 실행 (로그인 다이얼로그 → 메인 윈도우)
```

### DB
```bash
# 스키마 초기화 (SQL 직접)
mysql -u dc_user -p dc_db < db/schema.sql

# 마이그레이션 (User 테이블 포함)
cd server && ../.venv/bin/alembic upgrade head
cd server && ../.venv/bin/alembic revision --autogenerate -m "설명"

# 샘플 데이터
mysql -u dc_user -p dc_db < db/seeds/sample_data.sql
```

### 빌드
```bash
cd client && .venv/bin/pyinstaller build/client.spec  # exe 빌드
```

### 초기 관리자 비밀번호 해시 생성
```bash
# server/.env 의 ADMIN_PASSWORD_HASH 값 생성
cd server && ../.venv/bin/python -c \
  "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('비밀번호'))"
```

## 화면 흐름

```
main.py 실행
    └→ LoginDialog (POST /api/v1/auth/login → JWT 수신)
         └→ MainWindow (QStackedWidget)
              ├→ [0] HomePage — 측정 항목 카드 그리드 (기본 화면)
              ├→ [1] DCBiasMeasurementPage — DC Bias 전압 스윕 (전용 페이지)
              └→ [2+] MeasurementPage — 기타 측정 항목 (카드 클릭 시 생성)
                   └→ 뒤로가기 → HomePage 복귀
```

## 아키텍처

```
[클라이언트]
main.py → LoginDialog → JWT 획득
               ↓
          MainWindow (QStackedWidget)
               ↓ 카드 클릭
     ┌─────────────────────────────────────────────────────┐
     │ HomePage (3종 카드)                                  │
     │  ├─ DC-bias          → DCBiasMeasurementPage        │
     │  ├─ HALT / 8585      → MeasurementPage              │
     │  └─ 광학 설계분석    → MeasurementPage (이미지 업로드) │
     └─────────────────────────────────────────────────────┘
               ↓ (DC-bias / HALT·8585) 측정 시작 (QThread)
     MeasurementEngine → InstrumentRegistry → Driver → GPIB 계측기
                                                            ↓
                                                    APIClient (JWT 헤더)
                                                            ↓
                                                          Server

               ↓ (광학 설계분석) 이미지 파일 선택 → multipart 업로드
                                                    APIClient → POST /optical/upload

[서버]
POST /api/v1/auth/login     → JWT 발급
POST /api/v1/measurements   → MeasurementService → CRUD → MariaDB
POST /api/v1/optical/upload → 이미지 저장(UUID 파일명) + optical_analyses 레코드 생성
GET  /api/v1/optical/records → 업로드 이력 조회
GET  /                       → Jinja2 웹 대시보드 (FastAPI 직접 서빙)
```

- **단위 정규화**: `server/app/services/normalizer.py`에서 수신값을 표준 단위(F, Ω, V)로 변환 후 저장
- **측정 함수**: E4980A는 `CPD` 모드(Cp + 손실계수 D) 사용 — MLCC DC Bias 평가 표준
- **파일 업로드 경로**: `{UPLOAD_DIR}/optical/{uuid}.{ext}` (서버 로컬 디스크)

## 계측기 드라이버 추가

1. `client/app/instruments/drivers/{type}/{model}.py` 생성
2. `@InstrumentRegistry.register("MODEL_NAME")` 데코레이터 적용
3. `BaseLCRMeter` 또는 `BaseInstrument`의 추상 메서드 구현
4. LCR 미터의 경우 `disable_dc_bias()` 도 구현 (DC Bias 스윕 후 DUT 보호)
5. 등록 시 GUI 계측기 목록에 자동 반영

## API 엔드포인트

### 인증
`POST /api/v1/auth/login`
```json
{ "username": "string", "password": "string" }
→ { "access_token": "...", "token_type": "bearer", "username": "string" }
```

### GPIB 측정 데이터 (DC-bias / HALT·8585 모듈 공용)
`POST /api/v1/measurements` — `MeasurementSessionCreate`

```json
{
  "client_id": "string",
  "module_type": "dc_bias | halt_8585",
  "session_name": "string (optional)",
  "operator": "string (optional)",
  "instrument": {
    "model": "string",
    "gpib_address": 0,
    "type": "string"
  },
  "measurements": [
    {
      "characteristic": "capacitance|esr|df|impedance|q_factor|dc_bias",
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

### 광학 설계분석 이미지 업로드
`POST /api/v1/optical/upload` — multipart/form-data

| 필드 | 타입 | 설명 |
|------|------|------|
| `file` | File | 이미지 파일 (JPEG/PNG/BMP/TIFF/WebP, 최대 50 MB) |
| `operator` | Form (optional) | 작업자명 |
| `session_name` | Form (optional) | 세션명 |
| `description` | Form (optional) | 설명 |

```json
→ { "id": 1, "original_filename": "sample.jpg", "file_size": 204800,
    "uploaded_at": "2026-02-28T10:00:00Z", "status": "uploaded" }
```

`GET /api/v1/optical/records` — 이미지 업로드 이력 조회
- Query params: `page` (기본 1), `size` (기본 20), `operator` (optional)

## 환경 변수

`server/.env`
```
DB_HOST=
DB_PORT=
DB_NAME=
DB_USER=
DB_PASSWORD=
CORS_ORIGINS=

# JWT 인증
SECRET_KEY=change-me-in-production
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=480

# 초기 관리자 계정 (DB Users 테이블이 비어있을 때 사용)
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=         # bcrypt 해시값 (위 명령어로 생성)

# 파일 업로드 디렉터리 (광학 설계분석 이미지 저장 경로)
UPLOAD_DIR=uploads           # 상대 경로 또는 절대 경로
```

`client/.env`
```
API_BASE_URL=
API_TIMEOUT=
```
