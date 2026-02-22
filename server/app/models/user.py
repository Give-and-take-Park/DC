from sqlalchemy import Column, Integer, String
from app.db.base import Base


class User(Base):
    """사용자 계정 (로그인 인증용)"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
