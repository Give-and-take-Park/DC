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

    # JWT
    secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 480  # 8시간

    # 초기 관리자 계정 (.env로 재정의 가능)
    admin_username: str = "admin"
    admin_password_hash: str = ""  # hash_password()로 생성한 값을 .env에 설정

    # 파일 업로드
    upload_dir: str = "uploads"  # 상대 경로 또는 절대 경로

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    class Config:
        env_file = ".env"
