"""측정값 극단치 탐지 테스트."""
from __future__ import annotations

import pandas as pd

from src.spc.value_extreme_detection import (
    detect_value_extremes,
    filter_sample_excluding_extremes,
    spec_near_zero,
)


def test_zero_value_outlier_when_spec_not_near_zero():
    df = pd.DataFrame({"value": [10.1, 10.2, 0.0, 10.15, 10.05]})
    report = detect_value_extremes(df, usl=10.5, lsl=9.5)
    assert report.has_extremes
    codes = {p.reason_code for p in report.points}
    assert "ZERO_VALUE" in codes
    assert len(report.points) == 1


def test_zero_value_normal_when_spec_near_zero():
    df = pd.DataFrame({"value": [0.0, 0.01, 0.02, -0.01]})
    assert spec_near_zero(0.02, -0.02, df["value"].to_numpy())
    report = detect_value_extremes(df, usl=0.02, lsl=-0.02)
    assert not report.has_extremes


def test_significantly_above_usl():
    df = pd.DataFrame({"value": [10.0, 10.1, 15.0, 10.05]})
    report = detect_value_extremes(df, usl=10.5, lsl=9.5)
    assert any(p.reason_code == "ABOVE_USL" for p in report.points)


def test_filter_sample_drops_incomplete_subgroup():
    df = pd.DataFrame({
        "value": [1.0, 0.0, 4.0, 5.0],
        "subgroup_id": [1, 1, 2, 2],
    })
    # index 1 제거 → subgroup 1 불완전(1행) → 해당 subgroup 제거
    filtered = filter_sample_excluding_extremes(df, [1], subgroup_size=2)
    assert len(filtered) == 2
    assert filtered["subgroup_id"].nunique() == 1
    assert list(filtered["value"]) == [4.0, 5.0]
