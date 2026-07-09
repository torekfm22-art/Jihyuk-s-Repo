"""분석 대상(측정 포인트) 선택 — 세션·매칭 테스트."""
from __future__ import annotations

from src.spc.characteristic_split import normalize_split_value
from src.spc.pipeline import SpcPipelineResult
from src.spc_streamlit.analysis_runner import get_active_result, list_analysis_targets


def test_normalize_split_value_float_int():
    assert normalize_split_value(1.0) == "1"
    assert normalize_split_value("2.0") == "2"
    assert normalize_split_value("A") == "A"


def test_get_active_result_matches_float_keys():
    pipe = SpcPipelineResult(
        split_results=[
            SpcPipelineResult(characteristic="1", sample_count=10),
            SpcPipelineResult(characteristic="2.0", sample_count=11),
            SpcPipelineResult(characteristic="3", sample_count=12),
        ],
        split_column="measurement_point",
    )
    targets = list_analysis_targets(pipe)
    assert targets == ["1", "2.0", "3"]
    active = get_active_result(pipe, "2")
    assert normalize_split_value(active.characteristic) == "2"
