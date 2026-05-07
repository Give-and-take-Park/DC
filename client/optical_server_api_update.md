# 광학 서버 API 업데이트 내역

**업데이트 일자**: 2026-05-08  
**대상**: 분석 완료 확인 로직을 동기 응답(경우 1) 방식으로 구현

---

## 변경된 서버 파일

### 1. `server/app/models/optical.py` — 컬럼 추가

`optical_analyses` 테이블에 아래 컬럼 4개가 추가되었습니다.

| 컬럼 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `lot_no` | `String(20)` | `NULL` | 업로드 시 클라이언트가 전달하는 Lot No |
| `status` | `String(20)` | `"uploaded"` | `uploaded` → `analyzed` / `failed` |
| `result_filename` | `String(255)` | `NULL` | 결과 ZIP 서버 저장명 |
| `analyzed_at` | `DateTime` | `NULL` | 분석 완료 시각 |

> **DB 마이그레이션 필요** — 서버에서 아래 명령 실행:
> ```bash
> cd server
> ../.venv/bin/alembic revision --autogenerate -m "add lot_no status result_filename analyzed_at to optical_analyses"
> ../.venv/bin/alembic upgrade head
> ```

---

### 2. `server/app/schemas/optical.py` — 스키마 변경

#### 신규 스키마
```python
class OpticalAnalyzeRequest(BaseModel):
    record_id: int

class OpticalAnalyzeResponse(BaseModel):
    record_id: int
    status: str
    result_filename: Optional[str] = None
```

#### 기존 스키마 필드 추가
- `OpticalUploadResponse` — `lot_no` 필드 추가
- `OpticalAnalysisOut` — `lot_no`, `status`, `analyzed_at` 필드 추가

---

### 3. `server/app/api/v1/endpoints/optical.py` — 엔드포인트 변경

#### `POST /api/v1/optical/upload` (수정)
- 허용 Content-Type에 ZIP 추가: `application/zip`, `application/x-zip-compressed`, `application/octet-stream`
- `lot_no` Form 파라미터 추가 → DB 저장

#### `POST /api/v1/optical/analyze` (신규)
- 요청 바디: `{"record_id": int}`
- **분석이 완료될 때까지 HTTP 연결을 유지하고 응답 반환** (동기 방식)
- 이미 분석된 레코드는 기존 결과를 즉시 반환
- 분석 성공 시 `status → "analyzed"`, 결과 ZIP을 `{UPLOAD_DIR}/optical/results/`에 저장
- 분석 실패 시 `status → "failed"`, HTTP 500 반환
- 실제 분석 로직은 엔드포인트 내 주석 구간에 추가:
  ```python
  # ── 실제 분석 로직을 여기에 구현 ──
  ```

#### `GET /api/v1/optical/result/{record_id}` (신규)
- `status == "analyzed"` 인 레코드의 결과 ZIP을 `FileResponse`로 반환
- 다운로드 파일명: `{lot_no}_result.zip`

---

## 클라이언트-서버 파이프라인 흐름

```
클라이언트 (_PipelineWorker)          서버
─────────────────────────────────────────────────────────
1. ZIP 압축 (로컬)
2. POST /optical/upload ─────────────→ ZIP 저장 + DB 레코드 생성
   ← {id, lot_no, status:"uploaded"} ←
3. POST /optical/analyze ────────────→ 분석 실행 (완료까지 대기)
   ← {record_id, status:"analyzed"} ← 분석 완료 후 응답
4. GET  /optical/result/{id} ────────→ 결과 ZIP FileResponse
   ← result bytes                   ←
5. 결과 저장 (~/Documents/RIMS/results/{lot_no}_result.zip)
```

`/analyze` 엔드포인트가 분석 완료 전까지 응답을 보내지 않으므로,
클라이언트의 현재 파이프라인 코드(폴링 없음)가 그대로 동작합니다.
