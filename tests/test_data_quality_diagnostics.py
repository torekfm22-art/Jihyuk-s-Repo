"""데이터 품질 진단 테스트."""
from __future__ import annotations

import pandas as pd

from src.spc.data_quality_diagnostics import analyze_data_quality


def test_detect_mixed_measurement_points():
    df = pd.DataFrame({
        "measurement_point": ["1", "1", "2", "2", "3"],
        "value": [1.16, 1.16, 1.17, 1.17, 1.18],
        "timestamp": pd.date_range("2026-05-01", periods=5, freq="D"),
    })
    report = analyze_data_quality(df)
    codes = [f.code for f in report.findings]
    assert "MIXED_MEASUREMENT_POINTS" in codes


def test_detect_discrete_values():
    df = pd.DataFrame({
        "measurement_point": ["1"] * 20,
        "value": [1.16] * 10 + [1.17] * 7 + [1.18] * 3,
    })
    report = analyze_data_quality(df)
    codes = [f.code for f in report.findings]
    assert "DISCRETE_VALUES" in codes or "MULTIMODAL_CLUSTERS" in codes


def test_time_order_mismatch():
    df = pd.DataFrame({
        "value": [1.1, 1.2, 1.3],
        "timestamp": ["2026-06-03", "2026-06-01", "2026-06-02"],
    })
    report = analyze_data_quality(df)
    assert "TIME_ORDER_MISMATCH" in [f.code for f in report.findings]
