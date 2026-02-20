from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # DB
    db_host: str = "localhost"
    db_port: int = 3306
    db_name: str = "dc_db"
    db_user: str = "dc_user"
    db_password: str = ""

    # CORS
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:8000"]

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    class Config:
        env_file = ".env"
