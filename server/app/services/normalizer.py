"""MLCC 특성값 단위 정규화"""

from typing import Tuple

# 특성별 단위 → 표준 단위 변환 계수
_UNIT_FACTORS: dict[str, dict[str, float]] = {
    "capacitance": {
        "F": 1.0,
        "mF": 1e-3,
        "uF": 1e-6,
        "µF": 1e-6,
        "nF": 1e-9,
        "pF": 1e-12,
    },
    "esr": {
        "Ω": 1.0,
        "ohm": 1.0,
        "mΩ": 1e-3,
        "kΩ": 1e3,
    },
    "impedance": {
        "Ω": 1.0,
        "ohm": 1.0,
        "mΩ": 1e-3,
        "kΩ": 1e3,
    },
    "df": {
        "": 1.0,
        "%": 1e-2,
    },
    "q_factor": {
        "": 1.0,
    },
    "dc_bias": {
        "V": 1.0,
        "mV": 1e-3,
    },
}

# 특성별 표준 단위
_CANONICAL_UNIT: dict[str, str] = {
    "capacitance": "F",
    "esr": "Ω",
    "impedance": "Ω",
    "df": "",
    "q_factor": "",
    "dc_bias": "V",
}


def normalize_unit(characteristic: str, value: float, unit: str) -> Tuple[float, str]:
    """주어진 특성값을 표준 단위로 변환한다.

    알 수 없는 단위는 변환 없이 그대로 반환한다.
    """
    table = _UNIT_FACTORS.get(characteristic, {})
    factor = table.get(unit)
    if factor is None:
        return value, unit
    canonical = _CANONICAL_UNIT[characteristic]
    return value * factor, canonical
