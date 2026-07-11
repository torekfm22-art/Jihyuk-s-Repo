"""그룹별 규격(per_split_spec) 일괄 분석."""
from __future__ import annotations

import pandas as pd
import pytest

from src.spc.characteristic_split import COMPOSITE_SPLIT_COLUMN, apply_composite_split_column
from src.spc.pipeline import SpcJobConfig, SpcPipeline
from src.spc.spec_limits import preview_group_spec_limits, resolve_subset_spec_limits
from src.spc_streamlit.report_export import summary_file_tag


def test_resolve_subset_spec_limits_per_group():
    df_a = pd.DataFrame({"value": [1.0, 1.1], "usl": [5.0, 5.0], "lsl": [0.0, 0.0]})
    df_b = pd.DataFrame({"value": [2.0, 2.1], "usl": [8.0, 8.0], "lsl": [1.0, 1.0]})
    usl_a, lsl_a, _ = resolve_subset_spec_limits(df_a)
    usl_b, lsl_b, _ = resolve_subset_spec_limits(df_b)
    assert usl_a == 5.0 and lsl_a == 0.0
    assert usl_b == 8.0 and lsl_b == 1.0


def test_preview_group_spec_limits_composite():
    df = pd.DataFrame({
        "characteristic": ["검사A", "검사A", "검사B", "검사B"],
        "item": ["차종1", "차종1", "차종2", "차종2"],
        "value": [1.0, 1.1, 2.0, 2.1],
        "usl": [5.0, 5.0, 8.0, 8.0],
        "lsl": [0.0, 0.0, 1.0, 1.0],
        "timestamp": pd.date_range("2026-01-01", periods=4, freq="h"),
        "lot": ["L1", "L1", "L2", "L2"],
    })
    work = apply_composite_split_column(df, ["characteristic", "item"])
    rows = preview_group_spec_limits(
        work,
        COMPOSITE_SPLIT_COLUMN,
        ["검사A · 차종1", "검사B · 차종2"],
    )
    assert len(rows) == 2
    by_group = {r["그룹"]: r for r in rows}
    assert by_group["검사A · 차종1"]["USL"] == 5.0
    assert by_group["검사B · 차종2"]["USL"] == 8.0


def test_pipeline_per_split_spec_batch(tmp_path):
    rows = []
    specs = {
        ("검사A", "차종1"): (5.0, 0.0),
        ("검사B", "차종2"): (8.0, 1.0),
    }
    for (char, item), (usl, lsl) in specs.items():
        for i in range(30):
            rows.append({
                "characteristic": char,
                "item": item,
                "value": 1.0 + i * 0.001,
                "usl": usl,
                "lsl": lsl,
                "timestamp": pd.Timestamp("2026-06-01") + pd.Timedelta(minutes=i),
                "lot": f"LOT-{i // 5 + 1:03d}",
            })
    df = pd.DataFrame(rows)
    xlsx = tmp_path / "factory.xlsx"
    df.to_excel(xlsx, index=False)

    cfg = SpcJobConfig(
        input_files=[str(xlsx)],
        usl=99.0,
        lsl=-99.0,
        per_split_spec=True,
        chart_type="imr",
        imr_sampling_unit="lot",
        n_subgroups=10,
        measurement_point_mode="manual",
        measurement_point_columns=["characteristic", "item"],
        measurement_point_values=["검사A · 차종1", "검사B · 차종2"],
        output_dir=str(tmp_path / "out"),
        save_reports=False,
    )
    result = SpcPipeline(cfg).run()
    assert result.is_batch
    assert len(result.split_results) == 2
    caps = {c.characteristic: c.analysis.capability for c in result.split_results if c.analysis}
    assert caps["검사A · 차종1"].usl == 5.0
    assert caps["검사A · 차종1"].lsl == 0.0
    assert caps["검사B · 차종2"].usl == 8.0
    assert caps["검사B · 차종2"].lsl == 1.0


def test_summary_file_tag_composite():
    from src.spc.pipeline import SpcPipelineResult

    pipe = SpcPipelineResult(split_column=COMPOSITE_SPLIT_COLUMN)
    assert summary_file_tag(pipe) == "spc_composite_split"


def test_pipeline_manual_split_spec_limits(tmp_path):
    rows = []
    for name, lsl, usl in [("항목A", 0.0, 5.0), ("항목B", 1.0, 8.0)]:
        for i in range(30):
            rows.append({
                "characteristic": name,
                "value": 2.0 + i * 0.001,
                "timestamp": pd.Timestamp("2026-06-01") + pd.Timedelta(minutes=i),
                "lot": f"LOT-{i // 5 + 1:03d}",
            })
    xlsx = tmp_path / "manual_specs.xlsx"
    pd.DataFrame(rows).to_excel(xlsx, index=False)

    cfg = SpcJobConfig(
        input_files=[str(xlsx)],
        chart_type="imr",
        imr_sampling_unit="lot",
        n_subgroups=10,
        measurement_point_mode="manual",
        measurement_point_column="characteristic",
        measurement_point_values=["항목A", "항목B"],
        split_spec_limits={"항목A": (0.0, 5.0), "항목B": (1.0, 8.0)},
        output_dir=str(tmp_path / "out"),
        save_reports=False,
    )
    result = SpcPipeline(cfg).run()
    assert result.is_batch
    caps = {c.characteristic: c.analysis.capability for c in result.split_results if c.analysis}
    assert caps["항목A"].lsl == 0.0 and caps["항목A"].usl == 5.0
    assert caps["항목B"].lsl == 1.0 and caps["항목B"].usl == 8.0
