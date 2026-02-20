from typing import List, Optional
from app.instruments.registry import InstrumentRegistry
from app.instruments.base import BaseInstrument, MeasurementResult
from app.core.api_client import APIClient
from app.config.settings import Settings


class MeasurementEngine:
    """계측기 드라이버 로드·측정 실행·서버 전송을 조율하는 엔진"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.api_client = APIClient(settings)

    def load_instrument(self, model: str, resource_name: str) -> BaseInstrument:
        """레지스트리에서 드라이버를 조회하고 GPIB 연결을 맺는다."""
        driver_cls = InstrumentRegistry.get(model)
        instrument = driver_cls(resource_name)
        instrument.connect()
        return instrument

    def run_measurement(
        self,
        instrument: BaseInstrument,
        client_id: str,
        session_name: Optional[str] = None,
        **measure_kwargs,
    ) -> dict:
        """측정을 실행하고 결과를 서버에 전송한다."""
        results: List[MeasurementResult] = instrument.measure(**measure_kwargs)
        payload = self._build_payload(instrument, client_id, session_name, results)
        return self.api_client.send_measurements(payload)

    def _build_payload(
        self,
        instrument: BaseInstrument,
        client_id: str,
        session_name: Optional[str],
        results: List[MeasurementResult],
    ) -> dict:
        return {
            "client_id": client_id,
            "session_name": session_name,
            "instrument": {
                "model": type(instrument).__name__,
                "gpib_address": None,
                "type": instrument.instrument_type.value,
            },
            "measurements": [
                {
                    "characteristic": r.characteristic.value,
                    "value": r.value,
                    "unit": r.unit,
                    "frequency": r.frequency,
                    "dc_bias": r.dc_bias,
                    "temperature": r.temperature,
                    "raw_response": r.raw_response,
                }
                for r in results
            ],
        }

    def list_gpib_resources(self) -> List[str]:
        """GPIB에 연결된 리소스 주소 목록을 반환한다."""
        try:
            from app.instruments.gpib.connection import GPIBConnectionManager
            with GPIBConnectionManager() as mgr:
                return mgr.list_resources()
        except Exception:
            return []
