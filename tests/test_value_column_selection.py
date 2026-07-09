"""측정값 열 지정 — 유사 항목명 혼동 방지 테스트."""
from __future__ import annotations

import pandas as pd
import pytest

from src.spc.data_extractor import (
    MesQmsExtractor,
    _normalize_columns,
    _resolve_column_name,
    _suggest_value_columns,
    resolve_value_column_for_split_label,
)


def test_user_selected_column_not_overwritten_by_generic_value():
    """'바니쉬 중량' 지정 시 통용 '값' 열과 병합되지 않아야 함."""
    df = pd.DataFrame({
        "측정항목": ["바니쉬 중량", "바니쉬 후 스테이터 무게"],
        "값": [999.0, 888.0],
        "바니쉬 중량": [1.2, 1.3],
        "바니쉬 후 스테이터 무게": [10.1, 10.2],
    })
    col = _resolve_column_name(df, "바니쉬 중량")
    raw = df.rename(columns={col: "value"})
    out = _normalize_columns(raw)

    assert list(out.columns).count("value") == 1
    ext = MesQmsExtractor([out])
    result = ext.extract()
    assert list(result["value"]) == [1.2, 1.3]


def test_suggest_prefers_specific_column_over_generic_value():
    df = pd.DataFrame({
        "값": [1.0, 2.0],
        "바니쉬 중량": [1.1, 2.1],
        "바니쉬 후 스테이터 무게": [9.0, 9.1],
    })
    hints = _suggest_value_columns(df)
    assert hints[0] == "바니쉬 중량"
    assert "값" in hints
    assert hints.index("값") > hints.index("바니쉬 중량")


def test_resolve_rejects_ambiguous_partial_match():
    df = pd.DataFrame({
        "바니쉬 중량": [1.0],
        "바니쉬 후 스테이터 무게": [2.0],
    })
    with pytest.raises(ValueError, match="여러 컬럼과 부분 일치"):
        _resolve_column_name(df, "바니쉬")


def test_split_label_uses_matching_column():
    df = pd.DataFrame({
        "measure_item": ["바니쉬 중량", "바니쉬 후 스테이터 무게"],
        "value": [999.0, 999.0],
        "바니쉬 중량": [1.2, 1.3],
        "바니쉬 후 스테이터 무게": [10.1, 10.2],
    })
    subset = df[df["measure_item"] == "바니쉬 후 스테이터 무게"].copy()
    out = resolve_value_column_for_split_label(subset, "바니쉬 후 스테이터 무게")
    assert float(out["value"].iloc[0]) == 10.2
