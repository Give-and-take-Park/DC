from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    api_base_url: str = "http://localhost:8000"
    api_timeout: float = 10.0

    class Config:
        env_file = ".env"
