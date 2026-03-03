from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase
from app.core.config import Settings

settings = Settings()

engine = create_engine(settings.database_url, pool_pre_ping=True)


class Base(DeclarativeBase):
    pass


# Alembic autogenerate가 모든 모델을 탐색할 수 있도록 여기서 import
from app.models import measurement, instrument, user, optical  # noqa: E402, F401
