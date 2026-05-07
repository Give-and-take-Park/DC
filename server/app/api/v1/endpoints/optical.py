import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.base import settings
from app.db.session import get_db
from app.models.optical import OpticalAnalysis
from app.schemas.optical import (
    OpticalAnalysisOut,
    OpticalAnalyzeRequest,
    OpticalAnalyzeResponse,
    OpticalUploadResponse,
)

router = APIRouter()

_ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/bmp",
    "image/tiff",
    "image/webp",
    "application/zip",
    "application/x-zip-compressed",
    "application/octet-stream",
}
_MAX_FILE_MB = 50


@router.post("/upload", response_model=OpticalUploadResponse, status_code=201)
async def upload_optical_image(
    file: UploadFile = File(...),
    operator: Optional[str] = Form(None),
    lot_no: Optional[str] = Form(None),
    session_name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """광학 설계분석 ZIP 파일을 서버에 업로드합니다.

    - 지원 형식: ZIP, JPEG, PNG, BMP, TIFF, WebP
    - 최대 크기: 50 MB
    - 파일은 서버의 `{UPLOAD_DIR}/optical/` 디렉터리에 UUID 기반 이름으로 저장됩니다.
    """
    if file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail=(
                f"지원하지 않는 파일 형식입니다. "
                f"허용: ZIP, JPEG, PNG, BMP, TIFF, WebP"
            ),
        )

    content = await file.read()
    size_bytes = len(content)
    if size_bytes > _MAX_FILE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=(
                f"파일 크기({size_bytes // (1024 * 1024)} MB)가 "
                f"{_MAX_FILE_MB} MB를 초과합니다."
            ),
        )

    upload_dir = Path(settings.upload_dir) / "optical"
    upload_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "upload").suffix or ".bin"
    stored_name = f"{uuid.uuid4().hex}{ext}"
    (upload_dir / stored_name).write_bytes(content)

    record = OpticalAnalysis(
        operator=operator,
        lot_no=lot_no,
        session_name=session_name,
        original_filename=file.filename or stored_name,
        stored_filename=stored_name,
        file_size=size_bytes,
        description=description,
        status="uploaded",
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return OpticalUploadResponse(
        id=record.id,
        original_filename=record.original_filename,
        file_size=record.file_size,
        lot_no=record.lot_no,
        uploaded_at=record.uploaded_at,
    )


@router.post("/analyze", response_model=OpticalAnalyzeResponse)
async def analyze_optical(
    body: OpticalAnalyzeRequest,
    db: Session = Depends(get_db),
):
    """업로드된 ZIP을 분석하고, 완료 후 결과를 반환합니다.

    분석이 끝날 때까지 HTTP 연결을 유지합니다 (동기 응답).
    이미 분석된 레코드는 기존 결과를 그대로 반환합니다.
    """
    record = db.get(OpticalAnalysis, body.record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="레코드를 찾을 수 없습니다.")

    if record.status == "analyzed":
        return OpticalAnalyzeResponse(
            record_id=record.id,
            status=record.status,
            result_filename=record.result_filename,
        )

    upload_dir = Path(settings.upload_dir) / "optical"
    src_path = upload_dir / record.stored_filename
    if not src_path.exists():
        raise HTTPException(status_code=404, detail="업로드 파일을 찾을 수 없습니다.")

    try:
        result_dir = upload_dir / "results"
        result_dir.mkdir(parents=True, exist_ok=True)
        result_name = f"result_{record.id}_{uuid.uuid4().hex[:8]}.zip"
        result_path = result_dir / result_name

        # ── 실제 분석 로직을 여기에 구현 ──────────────────────────────
        # (현재는 플레이스홀더: 업로드 ZIP의 파일 목록을 요약한 결과 ZIP 생성)
        with zipfile.ZipFile(src_path, "r") as src_zip:
            file_list = src_zip.namelist()

        with zipfile.ZipFile(result_path, "w", zipfile.ZIP_DEFLATED) as out_zip:
            with zipfile.ZipFile(src_path, "r") as src_zip:
                for name in file_list:
                    out_zip.writestr(name, src_zip.read(name))
            summary = (
                f"record_id : {record.id}\n"
                f"lot_no    : {record.lot_no or '-'}\n"
                f"operator  : {record.operator or '-'}\n"
                f"files     : {len(file_list)}\n"
                f"status    : analysis_complete\n"
            )
            out_zip.writestr("analysis_summary.txt", summary)
        # ─────────────────────────────────────────────────────────────

        record.status = "analyzed"
        record.result_filename = result_name
        record.analyzed_at = datetime.now(timezone.utc)
        db.commit()

        return OpticalAnalyzeResponse(
            record_id=record.id,
            status="analyzed",
            result_filename=result_name,
        )

    except Exception as exc:
        record.status = "failed"
        db.commit()
        raise HTTPException(
            status_code=500, detail=f"분석 처리 중 오류: {exc}"
        ) from exc


@router.get("/result/{record_id}")
def download_optical_result(
    record_id: int,
    db: Session = Depends(get_db),
):
    """분석 완료된 결과 ZIP 파일을 다운로드합니다."""
    record = db.get(OpticalAnalysis, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="레코드를 찾을 수 없습니다.")
    if record.status != "analyzed" or not record.result_filename:
        raise HTTPException(status_code=404, detail="분석 결과가 없습니다.")

    result_path = (
        Path(settings.upload_dir) / "optical" / "results" / record.result_filename
    )
    if not result_path.exists():
        raise HTTPException(status_code=404, detail="결과 파일을 찾을 수 없습니다.")

    download_name = f"{record.lot_no or record_id}_result.zip"
    return FileResponse(
        path=str(result_path),
        media_type="application/zip",
        filename=download_name,
    )


@router.get("/records", response_model=List[OpticalAnalysisOut])
def list_optical_records(
    page: int = 1,
    size: int = 20,
    operator: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """업로드된 광학 설계분석 목록을 최신순으로 반환합니다."""
    q = db.query(OpticalAnalysis)
    if operator:
        q = q.filter(OpticalAnalysis.operator == operator)
    q = q.order_by(OpticalAnalysis.uploaded_at.desc())
    return q.offset((page - 1) * size).limit(size).all()
