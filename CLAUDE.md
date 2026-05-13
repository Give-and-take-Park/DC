# CLAUDE.md

Raffaello Inspection & Metrology System. Python venv + systemd 기반 (Docker 미사용).

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
cd client && .venv/bin/pyinstaller build/client.spec  # → dist/RIMS.exe 생성
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
    └→ LoginDialog (Knox ID 입력 → api_client.log_access() fire-and-forget)
         └→ MainWindow (QStackedWidget, 창 타이틀: RIMS)
              ├→ [0] HomePage — 3종 모듈 카드 그리드 (기본 화면)
              ├→ [1] DCBiasMeasurementPage — DC Bias 전용 페이지
              └→ [2+] MeasurementPage — 기타 측정 항목 (카드 클릭 시 생성)
                   └→ 뒤로가기 → HomePage 복귀 (헤더 '홈으로' 버튼)
```

## 아키텍처

```
[클라이언트]
main.py → LoginDialog → Knox ID 입력 → log_access() fire-and-forget
               ↓
          MainWindow (QStackedWidget)
               ↓ 카드 클릭
     ┌─────────────────────────────────────────────────────┐
     │ HomePage (3종 카드)                                  │
     │  ├─ DC-bias          → DCBiasMeasurementPage        │
     │  ├─ HALT / 8585      → MeasurementPage              │
     │  └─ 광학 설계분석    → OpticalAnalysisPage           │
     └─────────────────────────────────────────────────────┘
               ↓ (DC-bias / HALT·8585) 측정 시작 (QThread)
     MeasurementEngine → InstrumentRegistry → Driver → GPIB 계측기
                                                            ↓
                                                    APIClient (JWT 헤더)
                                                            ↓
                                                          Server

               ↓ (광학 설계분석) _PipelineWorker (QThread) 5단계 파이프라인
                  1. 이미지 목록 ZIP 압축 (임시 파일)
                  2. POST /optical/upload → folder_name 수신
                  3. POST /optical/analyze → 서버 분석 완료 대기 (동기)
                  4. GET  /optical/result/{folder_name} → Excel 다운로드
                  5. ~/Downloads/{folder_name}_result.xlsx 저장

[서버]
POST /api/v1/auth/login              → JWT 발급
POST /api/v1/measurements            → MeasurementService → CRUD → MariaDB
POST /api/v1/optical/upload          → ZIP 수신 → 경로 A에 압축 해제 → folder_name 반환
POST /api/v1/optical/analyze         → 경로 A 이미지 분석 → 경로 B에 Excel 저장 → 동기 응답
GET  /api/v1/optical/result/{folder_name} → 경로 B의 Excel 파일 직접 반환
GET  /                               → Jinja2 웹 대시보드 (FastAPI 직접 서빙)
```

**광학 파일 저장 경로**
- 경로 A (업로드): `{UPLOAD_DIR}/optical/uploads/{folder_name}/` — ZIP 압축 해제 이미지
- 경로 B (결과): `{UPLOAD_DIR}/optical/results/{folder_name}/` — 분석 결과 Excel
- `folder_name` 형식: `{lot_no}_{YYYYMMDD_HHMMSS}` (업로드·분석·다운로드의 공통 키)
- 클라이언트 저장 경로: `~/Downloads/{folder_name}_result.xlsx`

- **단위 정규화**: `server/app/services/normalizer.py`에서 수신값을 표준 단위(F, Ω, V)로 변환 후 저장
- **측정 함수**: E4980A는 `CPD` 모드(Cp + 손실계수 D) 사용 — MLCC DC Bias 평가 표준
- **클라이언트 앱 이름**: Raffaello Inspection & Metrology System (약칭 **RIMS**)
  - 창 프레임 타이틀: `RIMS`
  - 헤더: `RIMS` (35px bold) + `Raffaello Inspection & Metrology System` (20px normal)
  - 로그인 카드 타이틀: `Raffaello Inspection` / `& Metrology System` (2줄)
  - 빌드 exe: `RIMS.exe`
  - 창 프레임 아이콘: `client/app/ui/styles/icon.ico`

## DC Bias 측정 결과 테이블 (dc_bias_page.py)

| 컬럼 | 헤더 표시 | 너비 |
|------|-----------|------|
| No. | No. | 45px |
| 유지 시간 | Time(s) ▼ | 85px |
| 주파수 | Freq.(Hz) ▼ | 85px |
| AC 레벨 | AC(V) ▼ | 85px |
| DC 바이어스 | DC(V) ▼ | 85px |
| CHIP n 정전용량 | Cp(nF) | 85px |
| CHIP n 손실계수 | DF | 85px |

- 모든 입력 셀: 숫자(0 이상 실수)만 허용
- Enter: 다음 행 이동 (마지막 행에서 자동 추가)
- Delete / Backspace: 선택 셀 삭제
- Ctrl+C: 선택 범위 복사
- CSV 헤더: `No., Time(s), Freq.(Hz), AC(V), DC(V), CHIP1_Cp, CHIP1_DF, …`

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

### 광학 설계분석 파이프라인

`POST /api/v1/optical/upload` — multipart/form-data

| 필드 | 타입 | 설명 |
|------|------|------|
| `file` | File | 이미지 ZIP 파일 (최대 50 MB) |
| `lot_no` | Form | Lot 번호 (7자리 영문+숫자) |
| `operator` | Form (optional) | 작업자명 |

```json
→ { "folder_name": "ABC1234_20260514_102030", "lot_no": "ABC1234",
    "operator": "홍길동", "status": "uploaded" }
```

`POST /api/v1/optical/analyze`

```json
{ "folder_name": "ABC1234_20260514_102030" }
→ { "folder_name": "ABC1234_20260514_102030", "status": "analyzed" }
```

`GET /api/v1/optical/result/{folder_name}` — 분석 결과 Excel 파일 직접 반환
- 응답: `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
- 다운로드 파일명: `{folder_name}_result.xlsx`

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
