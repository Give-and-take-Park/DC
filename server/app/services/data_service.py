from sqlalchemy.orm import Session
from app.schemas.data import DataIngestionRequest
from app.services.normalizer import Normalizer
from app.crud import data as crud_data


class DataService:
    def __init__(self, db: Session):
        self.db = db
        self.normalizer = Normalizer()

    def ingest(self, payload: DataIngestionRequest):
        """원본 데이터 저장 후 정규화하여 저장"""
        raw = crud_data.create_raw(self.db, payload)
        normalized = self.normalizer.normalize(payload.payload, payload.client_id)
        crud_data.create_normalized(self.db, raw.id, normalized)
        return raw

    def get_summary(self):
        """대시보드 요약 통계"""
        return crud_data.get_summary(self.db)

    def get_records(self, page: int, size: int):
        """정규화 데이터 페이지네이션 조회"""
        return crud_data.get_records(self.db, page=page, size=size)
