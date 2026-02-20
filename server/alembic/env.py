from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
from app.db.base import Base
from app.core.config import Settings

# 신규 모델 import – Alembic이 자동 감지할 수 있도록 반드시 포함
import app.models.instrument   # noqa: F401
import app.models.measurement  # noqa: F401

settings = Settings()
config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(url=settings.database_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
