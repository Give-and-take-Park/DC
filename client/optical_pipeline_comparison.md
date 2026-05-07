# 광학 파이프라인 코드 비교 분석

**비교 대상**
- 구 코드: `client/optic_tkinter.txt` (Tkinter 기반 초기 구현)
- 현 코드: `client/app/ui/pages/optical_page.py` > `_PipelineWorker` (PyQt6 기반 현행 구현)

---

## 공통 단계 구조 (5단계)

| 단계 | 구 코드 (optic_tkinter.txt) | 현 코드 (_PipelineWorker) |
|------|----------------------------|--------------------------|
| 1 | 폴더 압축 (`os.walk` 전체 탐색) | 선택 이미지 파일만 압축 |
| 2 | ZIP 업로드 (`POST /upload_zip`) | ZIP 업로드 (`POST /api/v1/optical/upload`) |
| 3 | 분석 요청 (`POST /analyze_optic`) | 분석 요청 (`POST /api/v1/optical/analyze`) |
| 4 | 결과 다운로드 (`GET /download_result`) | 결과 다운로드 (`GET /api/v1/optical/result/{id}`) |
| 5 | 완료 메시지 출력 | 완료 시그널 emit |

---

## 주요 차이점

### 1. 압축 대상 및 ZIP 저장 위치

| 항목 | 구 코드 | 현 코드 |
|------|---------|---------|
| 입력 방식 | **폴더 경로** 선택 → `os.walk`로 폴더 내 전체 파일 | **개별 이미지 파일** 선택 → `_items` 목록의 파일만 |
| ZIP 저장 위치 | 선택한 폴더 내부 (`folder/{lot_no}.zip`) | 시스템 temp 디렉터리 (`%TEMP%/rims_optical/{lot_no}.zip`) |

### 2. API 연결 키 (가장 중요한 차이)

```
구 코드:
  [업로드 응답] → output_filename 필드 → [분석 요청 바디 = 업로드 응답 전체]
                                         → [다운로드 파라미터 = output_filename]

현 코드:
  [업로드 응답] → id (record_id) → [분석 요청 바디 = {record_id}]
                                  → [다운로드 경로 = /result/{record_id}]
```

구 코드는 업로드 응답의 `output_filename`을 기준으로 결과를 다운로드하고,
현 코드는 업로드 응답의 `id`(record_id)를 공통 키로 3단계 모두를 연결합니다.

### 3. 분석 완료 확인 로직

```python
# 구 코드 — 분석 응답의 check 필드를 직접 검증
check_process = loads(req_process.text)
if (req_process.status_code != 200) or (check_process['check'] == 'error'):
    raise Exception("자동 분석 실패")

# 현 코드 — 분석 응답을 저장하지 않고 바로 다운로드로 진행
self._api.request_optical_analysis(record_id)   # 반환값 미사용
result_bytes = self._api.download_optical_result(record_id)
```

> **주의**: 현 코드는 서버 분석이 **동기적**(분석 완료 후 응답 반환)으로 설계되어 있다고 가정합니다.
> 서버 분석이 비동기라면 `analyze` 요청 직후 `download`를 시도할 때 결과가 준비되지 않았을 수 있습니다.

### 4. 스레딩 방식

| 항목 | 구 코드 | 현 코드 |
|------|---------|---------|
| 스레드 | `threading.Thread(daemon=True)` | `QThread` + `_PipelineWorker(QObject)` |
| UI 갱신 | `show_message()` 직접 호출 (스레드 안전 아님) | `stage_changed` 시그널 → 메인 스레드에서 안전하게 갱신 |
| HTTP 클라이언트 | `requests` | `httpx` (APIClient 래퍼) |

### 5. ZIP 정리 방식

```python
# 구 코드 — 업로드 성공 후 조건부 삭제 (오류 발생 시 temp ZIP 잔류 가능)
if os.path.exists(self.zip_path):
    os.remove(self.zip_path)

# 현 코드 — finally 블록에서 항상 삭제 (오류와 무관하게 정리 보장)
finally:
    if zip_path is not None:
        zip_path.unlink(missing_ok=True)
```

### 6. 결과 저장 위치

| 항목 | 구 코드 | 현 코드 |
|------|---------|---------|
| 결과 ZIP | 선택 폴더 내부 (`folder/{output_filename}.zip`) | `~/Documents/RIMS/results/{lot_no}_result.zip` |

---

## 종합 요약

전반적인 흐름(압축 → 업로드 → 분석 → 다운로드)은 동일하나, 현 코드가 다음 측면에서 개선되어 있습니다.

| 항목 | 평가 |
|------|------|
| 스레드 안전성 | Qt 시그널/슬롯 구조로 UI 갱신 안전 보장 |
| 임시 파일 관리 | `finally` 블록으로 항상 정리 |
| API 경로 | REST 규약 준수 (`/api/v1/optical/...`) |
| 결과 저장 | 사용자 문서 폴더(`~/Documents/RIMS/results/`)로 일관된 경로 |

현 코드의 잠재적 개선 포인트: `request_optical_analysis()` 반환값을 검증하거나,
서버 분석이 비동기인 경우 완료 여부를 폴링하는 로직 추가 검토.
