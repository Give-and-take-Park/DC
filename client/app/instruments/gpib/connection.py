from typing import List

try:
    import pyvisa
    _PYVISA_AVAILABLE = True
except ImportError:
    _PYVISA_AVAILABLE = False


class GPIBConnectionManager:
    """PyVISA ResourceManager 래퍼 – GPIB 리소스 관리"""

    def __init__(self):
        if not _PYVISA_AVAILABLE:
            raise RuntimeError(
                "pyvisa가 설치되지 않았습니다. 다음을 실행하세요: pip install pyvisa pyvisa-py"
            )
        self._rm = pyvisa.ResourceManager()

    def list_resources(self) -> List[str]:
        """연결된 GPIB 리소스 주소 목록을 반환한다."""
        return list(self._rm.list_resources())

    def open(self, resource_name: str):
        """리소스를 열고 pyvisa Resource 객체를 반환한다."""
        return self._rm.open_resource(resource_name)

    def close(self) -> None:
        self._rm.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
