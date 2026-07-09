"""결론 Excel 캐시 무효화 테스트."""
from __future__ import annotations

import numpy as np

from src.spc.pipeline import SpcPipelineResult
from src.spc.statistics import SpcAnalyzer
from src.spc_streamlit.session_context import pipeline_export_fingerprint
from tests.test_traceability_export import _minimal_decision


def _leaf(char: str, ppk: float = 1.2) -> SpcPipelineResult:
    vals = np.linspace(0.2, 0.25, 25)
    subgroups = np.array([vals[i : i + 5] for i in range(0, 25, 5)])
    analysis = SpcAnalyzer().analyze_xbar_r(subgroups, usl=5.0, lsl=0.1)
    decision = _minimal_decision(stable=True)
    return SpcPipelineResult(
        characteristic=char,
        sample_count=len(vals),
        analysis=analysis,
        decision=decision,
    )


def test_pipeline_export_fingerprint_changes_with_targets():
    pipe_a = SpcPipelineResult(
        split_column="measurement_point",
        split_results=[
            _leaf("Target_A"),
            _leaf("Target_B"),
        ],
    )
    pipe_b = SpcPipelineResult(
        split_column="measurement_point",
        split_results=[
            _leaf("Target_C"),
        ],
    )
    assert pipeline_export_fingerprint(pipe_a) != pipeline_export_fingerprint(pipe_b)


def test_pipeline_export_fingerprint_stable_for_same_pipe():
    pipe = _leaf("Single_Target")
    assert pipeline_export_fingerprint(pipe) == pipeline_export_fingerprint(pipe)
