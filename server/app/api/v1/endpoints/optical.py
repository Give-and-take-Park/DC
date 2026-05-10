import csv
import io
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.base import settings
from app.db.session import get_db
from app.schemas.optical import (
    OpticalAnalyzeRequest,
    OpticalAnalyzeResponse,
    OpticalUploadResponse,
)

router = APIRouter()

_ALLOWED_CONTENT_TYPES = {
    "application/zip",
    "application/x-zip-compressed",
    "application/octet-stream",
}
_MAX_FILE_MB = 50

# 경로 A: 압축 해제된 이미지 저장 경로
# 경로 B: 분석 결과(Excel) 저장 경로
def _uploads_base() -> Path:
    return Path(settings.upload_dir) / "optical" / "uploads"

def _results_base() -> Path:
    return Path(settings.upload_dir) / "optical" / "results"


def _safe_subdir(base: Path, folder_name: str) -> Path:
    """folder_name이 base 밖을 가리키면 400 에러를 발생시킨다."""
    target = (base / folder_name).resolve()
    if not target.is_relative_to(base.resolve()):
        raise HTTPException(status_code=400, detail="잘못된 폴더명입니다.")
    return target


@router.post("/upload", response_model=OpticalUploadResponse, status_code=201)
async def upload_optical_zip(
    file: UploadFile = File(...),
    operator: Optional[str] = Form(None),
    lot_no: str = Form(...),
    db: Session = Depends(get_db),
):
    """ZIP 파일을 받아 경로 A의 {lot_no}_{datetime} 폴더에 압축 해제하여 저장합니다.

    - 지원 형식: ZIP
    - 최대 크기: 50 MB
    - 반환: 생성된 폴더명 (이후 analyze / result API의 키로 사용)
    """
    if file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail="ZIP 파일만 업로드할 수 있습니다.",
        )

    content = await file.read()
    size_bytes = len(content)
    if size_bytes > _MAX_FILE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"파일 크기({size_bytes // (1024 * 1024)} MB)가 {_MAX_FILE_MB} MB를 초과합니다.",
        )

    # 폴더명 생성: {lot_no}_{YYYYMMDD_HHMMSS}
    now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    folder_name = f"{lot_no}_{now_str}"

    # 경로 A 하위에 압축 해제
    upload_dir = _uploads_base()
    target_dir = _safe_subdir(upload_dir, folder_name)
    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            for member in zf.infolist():
                # ZIP 내부 경로 탐색 공격 방지
                member_path = (target_dir / member.filename).resolve()
                if not member_path.is_relative_to(target_dir):
                    raise HTTPException(status_code=400, detail="ZIP 내부에 잘못된 경로가 포함되어 있습니다.")
                zf.extract(member, target_dir)
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="유효하지 않은 ZIP 파일입니다.")

    return OpticalUploadResponse(
        folder_name=folder_name,
        lot_no=lot_no,
        operator=operator,
        status="uploaded",
    )


@router.post("/analyze", response_model=OpticalAnalyzeResponse)
async def analyze_optical(
    body: OpticalAnalyzeRequest,
    db: Session = Depends(get_db),
):
    """경로 A의 폴더 내 이미지를 분석하고, 결과를 경로 B의 동일 폴더명에 저장합니다.

    분석이 완료될 때까지 HTTP 연결을 유지합니다 (동기 응답).
    """
    folder_name = body.folder_name

    # 경로 A 검증
    upload_dir = _safe_subdir(_uploads_base(), folder_name)
    if not upload_dir.exists():
        raise HTTPException(status_code=404, detail="업로드 폴더를 찾을 수 없습니다.")

    # 경로 B 생성
    result_dir = _safe_subdir(_results_base(), folder_name)
    result_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 분석 대상 이미지 목록 수집
        image_exts = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}
        image_files = sorted(
            f for f in upload_dir.rglob("*")
            if f.is_file() and f.suffix.lower() in image_exts
        )

        # ── 실제 분석 로직을 여기에 구현 ──────────────────────────────
        # 분석 결과를 Excel 형태로 result_dir 에 저장합니다.
        # (현재는 플레이스홀더: 이미지 목록을 CSV로 저장)
        csv_path = result_dir / f"{folder_name}_result.csv"
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["No.", "파일명", "분석 상태"])
            for i, img in enumerate(image_files, start=1):
                writer.writerow([i, img.name, "분석 완료 (플레이스홀더)"])
        # ─────────────────────────────────────────────────────────────

        return OpticalAnalyzeResponse(
            folder_name=folder_name,
            status="analyzed",
        )

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"분석 처리 중 오류: {exc}") from exc


@router.get("/result/{folder_name}")
def download_optical_result(folder_name: str):
    """경로 B의 분석 결과 파일을 ZIP으로 압축하여 반환합니다."""
    result_dir = _safe_subdir(_results_base(), folder_name)
    if not result_dir.exists():
        raise HTTPException(status_code=404, detail="분석 결과 폴더를 찾을 수 없습니다.")

    result_files = [f for f in result_dir.iterdir() if f.is_file()]
    if not result_files:
        raise HTTPException(status_code=404, detail="분석 결과 파일이 없습니다.")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in result_files:
            zf.write(f, f.name)
    buf.seek(0)

    download_name = f"{folder_name}_result.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{download_name}"'},
    )
