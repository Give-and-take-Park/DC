from typing import Any, Dict


class Normalizer:
    """
    수신된 원본 데이터를 정규화하는 클래스.
    도메인에 맞게 정규화 로직을 구현한다.
    """

    def normalize(self, raw_payload: Dict[str, Any], client_id: str) -> Dict[str, Any]:
        # TODO: 실제 정규화 로직 구현
        return {
            "client_id": client_id,
            "value": None,
            "label": None,
        }
