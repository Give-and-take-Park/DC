from typing import Dict, List, Type, TYPE_CHECKING

if TYPE_CHECKING:
    from app.instruments.base import BaseInstrument


class InstrumentRegistry:
    """계측기 드라이버 레지스트리.

    @InstrumentRegistry.register("E4980A") 데코레이터로 드라이버를 등록한다.
    """

    _registry: Dict[str, Type["BaseInstrument"]] = {}

    @classmethod
    def register(cls, model: str):
        """드라이버 클래스를 모델명으로 등록하는 데코레이터."""
        def decorator(driver_cls: Type["BaseInstrument"]):
            cls._registry[model.upper()] = driver_cls
            return driver_cls
        return decorator

    @classmethod
    def get(cls, model: str) -> Type["BaseInstrument"]:
        """모델명으로 드라이버 클래스를 조회한다."""
        key = model.upper()
        if key not in cls._registry:
            registered = list(cls._registry.keys())
            raise KeyError(
                f"알 수 없는 계측기 모델: '{model}'. 등록된 모델: {registered}"
            )
        return cls._registry[key]

    @classmethod
    def list_models(cls) -> List[str]:
        """등록된 모델명 목록을 반환한다."""
        return list(cls._registry.keys())
