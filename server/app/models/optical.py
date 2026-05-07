from sqlalchemy import BigInteger, Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func
from app.db.base import Base


class OpticalAnalysis(Base):
    """광학 설계분석 이미지 업로드 기록.

    계측기 GPIB 연결 없이 사용자가 별도로 저장한 이미지(JPEG/PNG/BMP/TIFF/WebP)를
    서버에 전송·보관하는 모듈의 데이터 레코드.
    """
    __tablename__ = "optical_analyses"

    id                = Column(Integer, primary_key=True, index=True)
    operator          = Column(String(100), nullable=True, index=True)
    lot_no            = Column(String(20),  nullable=True, index=True)
    session_name      = Column(String(200), nullable=True)
    original_filename = Column(String(255), nullable=False)   # 원본 파일명
    stored_filename   = Column(String(255), nullable=False)   # UUID 기반 서버 저장명
    file_size         = Column(BigInteger,  nullable=True)    # bytes
    description       = Column(Text,        nullable=True)
    status            = Column(String(20),  nullable=False, server_default="uploaded")
    result_filename   = Column(String(255), nullable=True)    # 결과 ZIP 서버 저장명
    uploaded_at       = Column(DateTime(timezone=True),
                               server_default=func.now(), index=True)
    analyzed_at       = Column(DateTime(timezone=True), nullable=True)
