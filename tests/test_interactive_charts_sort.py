"""시계열 차트 정렬 테스트."""
from __future__ import annotations

import pandas as pd

from src.spc.interactive_charts import _sort_sample_for_chart
from src.spc.sample_ordering import sort_sample_dataframe


def test_sort_sample_by_timestamp():
    df = pd.DataFrame({
        "value": [3, 1, 2],
        "timestamp": ["2026-06-03", "2026-06-01", "2026-06-02"],
    })
    out = _sort_sample_for_chart(df)
    assert list(out["value"]) == [1, 2, 3]
    assert list(sort_sample_dataframe(df)["value"]) == [1, 2, 3]


def test_sort_subgroups_by_earliest_timestamp():
    df = pd.DataFrame({
        "value": [10, 11, 20, 21],
        "timestamp": ["2026-06-05", "2026-06-06", "2026-06-01", "2026-06-02"],
        "subgroup_id": [2, 2, 1, 1],
    })
    out = sort_sample_dataframe(df)
    assert list(out["subgroup_id"]) == [1, 1, 2, 2]
    assert list(out["value"]) == [20, 21, 10, 11]


def test_subgroup_hover_shows_date_and_violation_type():
    from src.spc.interactive_charts import _subgroup_hover

    df = pd.DataFrame({
        "subgroup_id": [1, 1, 2, 2],
        "value": [10.0, 10.1, 11.0, 11.1],
        "measure_time": pd.to_datetime([
            "2026-06-01 08:00", "2026-06-01 08:05",
            "2026-06-02 09:00", "2026-06-02 09:05",
        ]),
        "sampling_date": ["2026-06-01", "2026-06-01", "2026-06-02", "2026-06-02"],
    })
    text = _subgroup_hover(df, 1, 10.05, point_labels={2: ["한쪽 집중 (Shift)"]})
    assert "검사일" in text or "채취일" in text
    text2 = _subgroup_hover(df, 2, 11.05, point_labels={2: ["한쪽 집중 (Shift)"]})
    assert "이상 유형" in text2
    assert "Shift" in text2


def test_sort_subgroups_by_measure_time():
    df = pd.DataFrame({
        "value": [10, 11, 20, 21],
        "measure_time": ["2026-06-05", "2026-06-06", "2026-06-01", "2026-06-02"],
        "subgroup_id": [2, 2, 1, 1],
    })
    out = sort_sample_dataframe(df)
    assert list(out["subgroup_id"]) == [1, 1, 2, 2]
    assert list(out["value"]) == [20, 21, 10, 11]
