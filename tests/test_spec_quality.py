"""그룹별 규격 품질 감지."""
from __future__ import annotations

import pandas as pd

from src.spc.spec_limits import assess_group_spec_quality, assess_spec_values_quality


def test_assess_group_spec_missing():
    df = pd.DataFrame({"value": [1.0, 2.0]})
    warn, status, issues = assess_group_spec_quality(df, lsl=None, usl=None)
    assert warn is True
    assert status == "미감지"
    assert "미감지" in issues


def test_assess_group_spec_text_in_column():
    df = pd.DataFrame({"value": [1.0], "usl": ["MAX"], "lsl": [0.0]})
    warn, status, issues = assess_group_spec_quality(df, lsl=0.0, usl=None)
    assert warn is True
    assert "USL 텍스트" in issues


def test_assess_group_spec_mixed_values():
    df = pd.DataFrame({"usl": [5.0, 6.0], "lsl": [0.0, 0.0]})
    warn, _, issues = assess_group_spec_quality(df, lsl=0.0, usl=5.0)
    assert warn is True
    assert "USL 혼재" in issues


def test_assess_spec_values_ok_after_edit():
    warn, status, _ = assess_spec_values_quality(0.0, 5.0)
    assert warn is False
    assert status == "OK"


def test_filter_groups_by_excluded():
    from src.spc.characteristic_split import normalize_split_value
    from src.spc_streamlit.components import _filter_groups_by_excluded

    groups = ["A", "B", "C"]
    out = _filter_groups_by_excluded(
        groups, {normalize_split_value("B")}, normalize=normalize_split_value,
    )
    assert out == ["A", "C"]


def test_is_row_selected_variants():
    from src.spc_streamlit.components import _is_row_selected

    assert _is_row_selected(True) is True
    assert _is_row_selected(False) is False
    assert _is_row_selected(1) is True
    assert _is_row_selected(0) is False
    assert _is_row_selected("true") is True
    assert _is_row_selected(None) is False


def test_build_split_pick_df_min_rows():
    from src.spc_streamlit.components import MIN_SPLIT_ROW_COUNT, _build_split_pick_df

    summary = [
        {"point_id": "A", "row_count": 100, "period_start": "", "period_end": ""},
        {"point_id": "B", "row_count": 125, "period_start": "", "period_end": ""},
        {"point_id": "C", "row_count": 200, "period_start": "", "period_end": ""},
    ]
    df = _build_split_pick_df(
        summary,
        select_if=lambda s: int(s["row_count"]) >= MIN_SPLIT_ROW_COUNT,
    )
    assert not bool(df.loc[df["항목명"] == "A", "선택"].iloc[0])
    assert bool(df.loc[df["항목명"] == "B", "선택"].iloc[0])
    assert bool(df.loc[df["항목명"] == "C", "선택"].iloc[0])
