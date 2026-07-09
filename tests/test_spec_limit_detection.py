"""규격(공차) 자동 감지."""
from __future__ import annotations

import pandas as pd

from src.spc.data_extractor import (
    _normalize_columns,
    detect_spec_limits,
)


def test_detect_spec_from_han_sang_han_column_names():
    df = pd.DataFrame({
        "하한값": [9.5] * 10,
        "상한값": [10.5] * 10,
        "값": [10.0 + i * 0.01 for i in range(10)],
        "트랜잭션 시간": [f"2026-06-01 10:{i:02d}:00" for i in range(10)],
    })
    norm = _normalize_columns(df.copy())
    col_display = {"lsl": "하한값", "usl": "상한값"}
    sp = detect_spec_limits(df, norm, column_display=col_display)
    assert sp.detected
    assert sp.lsl == 9.5
    assert sp.usl == 10.5
    assert sp.suggested_spec_mode == "both"
    assert sp.lsl_display_column == "하한값"
    assert sp.usl_display_column == "상한값"


def test_detect_spec_from_constant_pattern_columns():
    df = pd.DataFrame({
        "spec_low": [8.0] * 8,
        "spec_high": [12.0] * 8,
        "value": [10.0] * 8,
    })
    norm = _normalize_columns(df.copy())
    sp = detect_spec_limits(df, norm)
    assert sp.detected
    assert sp.lsl == 8.0
    assert sp.usl == 12.0


def test_detect_spec_from_varying_named_columns_uses_dominant():
    """품목별 상이한 하한·상한이 섞여 있어도 명칭 열이면 대표값 추천."""
    df = pd.DataFrame({
        "하한값": [9.0, 9.0, 9.5, 9.5, 9.5],
        "상한값": [11.0, 11.0, 10.5, 10.5, 10.5],
        "값": [10.0] * 5,
    })
    norm = _normalize_columns(df.copy())
    sp = detect_spec_limits(df, norm)
    assert sp.detected
    assert sp.lsl == 9.5
    assert sp.usl == 10.5
