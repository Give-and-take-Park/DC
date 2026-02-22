import httpx
from typing import List, Optional
from app.config.settings import Settings


class APIClient:
    """FastAPI 서버와 통신하는 HTTP 클라이언트"""

    def __init__(self, settings: Settings):
        self.base_url = settings.api_base_url
        self.timeout = settings.api_timeout
        self._token: Optional[str] = None

    def set_token(self, token: str) -> None:
        """JWT 액세스 토큰을 설정한다."""
        self._token = token

    def _auth_headers(self) -> dict:
        if self._token:
            return {"Authorization": f"Bearer {self._token}"}
        return {}

    def login(self, username: str, password: str) -> dict:
        """서버에 로그인하고 JWT 토큰 응답을 반환한다."""
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/api/v1/auth/login",
                json={"username": username, "password": password},
            )
            response.raise_for_status()
            return response.json()

    def send_measurements(self, payload: dict) -> dict:
        """MLCC 측정 데이터를 서버에 전송한다."""
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/api/v1/measurements",
                json=payload,
                headers=self._auth_headers(),
            )
            response.raise_for_status()
            return response.json()

    def get_instruments(self) -> List[dict]:
        """서버에 등록된 계측기 목록을 조회한다."""
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(
                f"{self.base_url}/api/v1/instruments",
                headers=self._auth_headers(),
            )
            response.raise_for_status()
            return response.json()

    def check_server(self) -> bool:
        """서버 연결 상태를 확인한다."""
        try:
            with httpx.Client(timeout=3.0) as client:
                response = client.get(f"{self.base_url}/")
                return response.status_code < 500
        except Exception:
            return False
