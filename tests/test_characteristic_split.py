"""항목별 자동 분리 — 단위 테스트."""
from __future__ import annotations

import pandas as pd
import pytest

from src.spc.characteristic_split import detect_split_column, list_split_values, safe_filename_slug
from src.spc.pipeline import SpcJobConfig, SpcPipeline


def test_detect_split_column_characteristic():
    df = pd.DataFrame({
        "characteristic": ["높이#1", "높이#1", "높이#2", "높이#2"],
        "value": [1.0, 1.1, 2.0, 2.1],
    })
    assert detect_split_column(df) == "characteristic"
    assert list_split_values(df, "characteristic") == ["높이#1", "높이#2"]


def test_detect_split_column_measure_item():
    df = pd.DataFrame({
        "measure_item": ["A", "B"],
        "value": [1.0, 2.0],
    })
    assert detect_split_column(df) == "measure_item"


def test_safe_filename_slug():
    assert safe_filename_slug("높이 측정 데이터#4") == "높이_측정_데이터#4"


def test_pipeline_auto_split(tmp_path):
    rows = []
    for n in range(1, 4):
        for i in range(30):
            rows.append({
                "characteristic": f"항목#{n}",
                "value": 10.0 + n * 0.01 + i * 0.001,
                "timestamp": pd.Timestamp("2026-06-01") + pd.Timedelta(minutes=i + n * 100),
                "lot": f"LOT-{i // 5 + 1:03d}",
                "usl": 10.5,
                "lsl": 9.5,
            })
    df = pd.DataFrame(rows)
    xlsx = tmp_path / "test.xlsx"
    df.to_excel(xlsx, index=False)

    cfg = SpcJobConfig(
        input_files=[str(xlsx)],
        usl=10.5,
        lsl=9.5,
        chart_type="imr",
        imr_sampling_unit="lot",
        n_subgroups=10,
        output_dir=str(tmp_path / "out"),
    )
    result = SpcPipeline(cfg).run()
    assert result.is_batch
    assert len(result.split_results) == 3
    assert all(c.report_paths.get("excel") for c in result.split_results)
