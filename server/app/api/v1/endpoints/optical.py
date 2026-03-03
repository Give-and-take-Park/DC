import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db.base import settings
from app.db.session import get_db
from app.models.optical import OpticalAnalysis
from app.schemas.optical import OpticalAnalysisOut, OpticalUploadResponse

router = APIRouter()

_ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/bmp",
    "image/tiff",
    "image/webp",
}
_MAX_FILE_MB = 50


@router.post("/upload", response_model=OpticalUploadResponse, status_code=201)
async def upload_optical_image(
    file: UploadFile = File(...),
    operator: Optional[str] = Form(None),
    session_name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """광학 설계분석 이미지를 서버에 업로드합니다.

    - 지원 형식: JPEG, PNG, BMP, TIFF, WebP
    - 최대 크기: 50 MB
    - 파일은 서버의 `{UPLOAD_DIR}/optical/` 디렉터리에 UUID 기반 이름으로 저장됩니다.
    """
    if file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail=(
                f"지원하지 않는 파일 형식입니다. "
                f"허용: {', '.join(sorted(_ALLOWED_CONTENT_TYPES))}"
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

    # UUID 기반 파일명으로 저장 (원본 파일명 충돌 방지)
    upload_dir = Path(settings.upload_dir) / "optical"
    upload_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "image").suffix or ".bin"
    stored_name = f"{uuid.uuid4().hex}{ext}"
    (upload_dir / stored_name).write_bytes(content)

    record = OpticalAnalysis(
        operator=operator,
        session_name=session_name,
        original_filename=file.filename or stored_name,
        stored_filename=stored_name,
        file_size=size_bytes,
        description=description,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return OpticalUploadResponse(
        id=record.id,
        original_filename=record.original_filename,
        file_size=record.file_size,
        uploaded_at=record.uploaded_at,
    )


@router.get("/records", response_model=List[OpticalAnalysisOut])
def list_optical_records(
    page: int = 1,
    size: int = 20,
    operator: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """업로드된 광학 설계분석 이미지 목록을 최신순으로 반환합니다."""
    q = db.query(OpticalAnalysis)
    if operator:
        q = q.filter(OpticalAnalysis.operator == operator)
    q = q.order_by(OpticalAnalysis.uploaded_at.desc())
    return q.offset((page - 1) * size).limit(size).all()
