"""Streamlit 업로드 경로 — 절대 경로로 파이프라인에 전달되는지."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.spc.path_utils import resolve_input_path
from src.spc_streamlit.analysis_runner import run_spc_analysis


def test_resolve_input_absolute_upload_path(tmp_path):
    f = tmp_path / "SPC_RAW DATA_test.xlsx"
    pd.DataFrame({"value": [1.0, 2.0]}).to_excel(f, index=False)
    resolved = resolve_input_path(str(f.resolve()), tmp_path / "input")
    assert resolved == f.resolve()


def test_run_spc_analysis_uses_uploaded_file_not_data_input(tmp_path):
    xlsx = tmp_path / "SPC_RAW DATA_인플레이터 저항(SQUIB).xlsx"
    pd.DataFrame({
        "value": [10.0, 10.1, 10.2, 10.0, 10.1] * 30,
        "process": ["조립"] * 150,
        "characteristic": ["저항"] * 150,
    }).to_excel(xlsx, index=False)

    bundle = run_spc_analysis(
        [xlsx],
        usl=11.0,
        lsl=9.0,
        chart_type="imr",
        n_subgroups=25,
        output_dir=tmp_path / "out",
    )
    assert bundle.pipeline.sample_count > 0
