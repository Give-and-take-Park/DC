import httpx
from app.config.settings import Settings


class APIClient:
    """FastAPI 서버와 통신하는 HTTP 클라이언트"""

    def __init__(self, settings: Settings):
        self.base_url = settings.api_base_url
        self.timeout = settings.api_timeout

    def send_data(self, payload: dict) -> dict:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(f"{self.base_url}/api/v1/data", json=payload)
            response.raise_for_status()
            return response.json()
