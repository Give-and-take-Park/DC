from sqlalchemy import Column, Integer, String, Float, DateTime, JSON
from sqlalchemy.sql import func
from app.db.base import Base


class RawData(Base):
    """클라이언트에서 수신한 원본 데이터"""
    __tablename__ = "raw_data"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(String(100), nullable=False, index=True)
    raw_payload = Column(JSON, nullable=False)
    received_at = Column(DateTime(timezone=True), server_default=func.now())


class NormalizedData(Base):
    """정규화 처리된 데이터"""
    __tablename__ = "normalized_data"

    id = Column(Integer, primary_key=True, index=True)
    raw_data_id = Column(Integer, nullable=False, index=True)
    client_id = Column(String(100), nullable=False, index=True)
    # TODO: 도메인에 맞는 컬럼 추가
    value = Column(Float, nullable=True)
    label = Column(String(255), nullable=True)
    normalized_at = Column(DateTime(timezone=True), server_default=func.now())
