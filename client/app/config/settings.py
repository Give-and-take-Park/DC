from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    api_base_url: str = "http://localhost:8000"
    api_timeout: float = 10.0
    operator: str = ""  # 로그인 성공 후 username으로 설정됨

    class Config:
        env_file = ".env"
