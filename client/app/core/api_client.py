import httpx
from typing import List
from app.config.settings import Settings


class APIClient:
    """FastAPI 서버와 통신하는 HTTP 클라이언트"""

    def __init__(self, settings: Settings):
        self.base_url = settings.api_base_url
        self.timeout = settings.api_timeout

    def send_measurements(self, payload: dict) -> dict:
        """MLCC 측정 데이터를 서버에 전송한다."""
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/api/v1/measurements", json=payload
            )
            response.raise_for_status()
            return response.json()

    def get_instruments(self) -> List[dict]:
        """서버에 등록된 계측기 목록을 조회한다."""
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(f"{self.base_url}/api/v1/instruments")
            response.raise_for_status()
            return response.json()
