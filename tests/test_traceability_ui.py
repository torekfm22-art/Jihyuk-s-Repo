"""추적성 UI 테스트."""
from __future__ import annotations

import pandas as pd

from src.spc.chart_violations import expand_violation_row_indices
from src.spc.interactive_charts import build_traceability_raw_chart_figure


def test_expand_violation_rows_for_subgroup():
    df = pd.DataFrame({
        "value": [1.0, 1.1, 2.0, 2.1, 3.0],
        "subgroup_id": [1, 1, 2, 2, 3],
    })
    rows = expand_violation_row_indices(df, {2}, "xbar_s")
    assert rows == {3, 4}


def test_raw_chart_time_ordered_x_axis():
    df = pd.DataFrame({
        "value": [10.0, 10.2, 10.1, 10.3],
        "timestamp": pd.to_datetime([
            "2026-01-01 08:00",
            "2026-01-01 14:30",
            "2026-01-02 09:15",
            "2026-01-02 16:45",
        ]),
    })
    fig = build_traceability_raw_chart_figure(df)
    assert fig is not None
    assert fig.layout.xaxis.title.text == "측정 순서 (시간순 →)"
    assert fig.layout.xaxis.tickmode == "array"
    assert any(":" in str(t) for t in (fig.layout.xaxis.ticktext or []))


def test_raw_chart_with_subgroup_annotation():
    df = pd.DataFrame({
        "value": [10.0, 10.1, 15.0, 14.9],
        "subgroup_id": [1, 1, 2, 2],
        "lot": ["L1", "L1", "L2", "L2"],
        "timestamp": pd.date_range("2026-01-01", periods=4, freq="h"),
    })
    fig = build_traceability_raw_chart_figure(
        df,
        violation_points={3, 4},
        anomaly_subgroups={2},
        rule_labels_by_point={2: ["Shift"]},
        chart_type="xbar_s",
    )
    assert fig is not None
    assert len(fig.layout.annotations) >= 1
