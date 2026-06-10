"""데모/테스트용 샘플 데이터 - 확인된 구조만 반영."""
from __future__ import annotations

import pandas as pd


def build_demo_frequency_df() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "factory_name": "김천",
            "domain": "공정",
            "inspection_type": "순회검사",
            "line_name": "라인A",
            "inspection_name": "순회검사",
            "year": 2025,
            "month": 1,
            "quantity": 120,
        },
        {
            "factory_name": "김천",
            "domain": "입고",
            "inspection_type": "샘플링",
            "line_name": "",
            "inspection_name": "입고검사",
            "year": 2025,
            "month": 1,
            "quantity": 45,
        },
        {
            "factory_name": "충주",
            "domain": "완성",
            "inspection_type": "전수",
            "line_name": "라인B",
            "inspection_name": "완성전수검사",
            "year": 2025,
            "month": 2,
            "quantity": 80,
        },
    ])


def build_demo_unit_time_df() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "factory_name": "김천",
            "line_name": "라인A",
            "inspection_name": "순회검사",
            "movement_distance_m": 12.0,
            "weight_kg": 0,
            "mod_value": 5.0,
            "auxiliary_rate": 0.10,
            "measured_wait_sec": 30,
        },
        {
            "factory_name": "김천",
            "line_name": "",
            "inspection_name": "입고검사",
            "movement_distance_m": None,
            "mod_value": 3.0,
            "auxiliary_rate": 0.10,
            "measured_wait_sec": None,
        },
        {
            "factory_name": "충주",
            "line_name": "라인B",
            "inspection_name": "완성전수검사",
            "movement_distance_m": 6.0,
            "mod_value": 8.0,
            "auxiliary_rate": 0.10,
            "measured_wait_sec": 60,
        },
    ])
