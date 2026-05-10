# 광학 API 폴더명 기반 리팩토링

**업데이트 일자**: 2026-05-10  
**변경 요약**: 파이프라인 연결키를 `record_id` (DB 기반) → `folder_name` (파일 시스템 기반)으로 전환

---

## 변경 배경

기존 방식은 `upload → DB INSERT → record_id 반환 → analyze(record_id) → result(record_id)` 구조로,
파이프라인 전체가 DB에 의존했습니다.

새 방식은 `folder_name = {lot_no}_{YYYYMMDD_HHMMSS}` 문자열을 공통 키로 사용하여
파일 시스템만으로 3단계가 연결됩니다.

---

## 새 API 흐름

```
POST /api/v1/optical/upload
  - 클라이언트 ZIP 수신
  - 경로 A/{lot_no}_{YYYYMMDD_HHMMSS}/ 에 압축 해제하여 저장
  - 반환: { folder_name, lot_no, operator, status }

POST /api/v1/optical/analyze
  - 요청 바디: { "folder_name": "ABC1234_20260510_143022" }
  - 경로 A/folder_name/ 내 이미지 분석
  - 결과(Excel)를 경로 B/folder_name/ 에 저장
  - 분석 완료 후 응답 반환 (동기): { folder_name, status: "analyzed" }

GET /api/v1/optical/result/{folder_name}
  - 경로 B/folder_name/ 내 파일을 ZIP으로 압축하여 반환
  - 다운로드 파일명: {folder_name}_result.zip
```

**경로 A**: `{UPLOAD_DIR}/optical/uploads/{folder_name}/` — 압축 해제된 이미지  
**경로 B**: `{UPLOAD_DIR}/optical/results/{folder_name}/` — 분석 결과(Excel)

---

## 변경된 파일

### 서버

#### `server/app/schemas/optical.py`
- `OpticalUploadResponse`: `id` → `folder_name`, `lot_no`, `operator` 필드로 교체
- `OpticalAnalyzeRequest`: `record_id: int` → `folder_name: str`
- `OpticalAnalyzeResponse`: `record_id` → `folder_name`

#### `server/app/api/v1/endpoints/optical.py`
- `POST /upload`: ZIP 수신 → 경로 A에 압축 해제 → folder_name 반환
- `POST /analyze`: folder_name으로 경로 A 탐색 → 분석 → 경로 B에 저장 → 동기 응답
- `GET /result/{folder_name}`: 경로 B의 결과 파일을 ZIP StreamingResponse로 반환
- `_safe_subdir()`: folder_name이 base 경로 밖을 가리키면 HTTP 400 반환 (경로 탐색 공격 방지)
- ZIP 내부 경로 탐색 공격 방지 처리 추가

### 클라이언트

#### `client/app/core/api_client.py`
| 메서드 | 변경 내용 |
|--------|----------|
| `upload_optical_zip()` | 반환값에서 `id` 대신 `folder_name` 사용 |
| `request_optical_analysis(folder_name: str)` | 인자 `record_id: int` → `folder_name: str`, 요청 바디 변경 |
| `download_optical_result(folder_name: str)` | 인자 및 URL 경로 변경 |

#### `client/app/ui/pages/optical_page.py` — `_PipelineWorker.run()`
- 2단계: `upload_result.get("folder_name", lot_no)` 로 folder_name 추출
- 3단계: `request_optical_analysis(folder_name)`
- 4단계: `download_optical_result(folder_name)`
- 5단계: 저장 파일명 `{folder_name}_result.zip`

#### `client/tests/run_ui_preview.py` — `_MockAPIClient`
- `upload_optical_zip()`: `folder_name` 포함 응답 반환
- `request_optical_analysis(folder_name)`: 시그니처 및 반환값 변경
- `download_optical_result(folder_name)`: 시그니처 및 ZIP 내 파일명 변경

---

## 실제 분석 로직 구현 위치

`server/app/api/v1/endpoints/optical.py` — `analyze_optical()` 함수 내 주석 구간:

```python
# ── 실제 분석 로직을 여기에 구현 ──────────────────────────────
# 분석 결과를 Excel 형태로 result_dir 에 저장합니다.
# (현재는 플레이스홀더: 이미지 목록을 CSV로 저장)
...
# ─────────────────────────────────────────────────────────────
```

Excel 출력이 필요한 경우 `openpyxl` 패키지를 `server/requirements.txt`에 추가 후 사용합니다.
