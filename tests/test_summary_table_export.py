"""분석 대상별 판정 요약표 Excel."""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from src.spc.pipeline import SpcPipelineResult
from src.spc.statistics import SpcAnalyzer
from src.spc.summary_table_export import (
    SUMMARY_COLUMNS,
    _build_normality_remark,
    _build_mean_chart_remark,
    _compact_point_refs,
    build_summary_dataframe,
    build_summary_remarks,
    generate_summary_excel_bytes,
    iter_leaf_pipeline_results,
)
from src.spc.decision_models import CompanyChartDecision, ControlChartDecision
from tests.test_traceability_export import _minimal_decision


def _make_analysis(usl=5.0, lsl=0.1):
    vals = np.linspace(0.2, 0.25, 125)
    subgroups = np.array([vals[i : i + 5] for i in range(0, 125, 5)])
    return SpcAnalyzer().analyze_xbar_r(subgroups, usl=usl, lsl=lsl)


def test_compact_point_refs_ranges():
    pts = [1, 2, 3, 4, 5, 6, 7, 10, 11, 12, 13, 14, 15, 21, 22]
    assert _compact_point_refs(pts) == "#1~7, #10~15, #21~22"


def test_build_normality_remark_with_boxcox():
    analysis = _make_analysis()
    analysis.normality.is_normal = False
    decision = _minimal_decision(stable=True)
    decision.normality.is_normal = False
    decision.normality.transform_success = True
    decision.normality.transform_method = "box_cox"
    text = _build_normality_remark(analysis, decision)
    assert text == "정규성 비정규 판정, Box-cox 변환 O"


def test_build_normality_remark_false_positive_from_action_text():
    """권고 문구에만 'Box-Cox'가 있어도 변환 성공으로 표기하지 않음."""
    analysis = _make_analysis()
    analysis.normality.is_normal = False
    decision = _minimal_decision(stable=True)
    decision.normality.is_normal = False
    decision.normality.transform_success = False
    decision.normality.applied_action = (
        "Box-Cox·Johnson 변환, 비정규 적합, 비모수 capability 옵션 검토"
    )
    text = _build_normality_remark(analysis, decision)
    assert "Box-cox" not in text
    assert text == "정규성 미충족"


def test_build_normality_remark_transform_failed():
    analysis = _make_analysis()
    analysis.normality.is_normal = False
    decision = _minimal_decision(stable=True)
    decision.normality.is_normal = False
    decision.normality.transform_success = False
    decision.normality.transform_attempts = [
        {"method": "box_cox", "success": False, "is_normal_after": False},
        {"method": "johnson_su", "success": False, "is_normal_after": False},
    ]
    text = _build_normality_remark(analysis, decision)
    assert text == "정규성 미충족"


def test_mean_chart_remark_when_r_unstable_lists_xbar_points():
    analysis = _make_analysis()
    analysis.out_of_control_points = [1, 2, 3, 4, 19, 20, 21, 22, 23, 24, 25]
    decision = _minimal_decision(stable=False)
    decision.control_chart.company_interpretation = CompanyChartDecision(
        status="비관리상태",
        detected_rules=[],
        summary_message="",
        actions=[],
        mean_chart_deferred=True,
        dispersion_abnormal=True,
    )
    text = _build_mean_chart_remark(analysis, decision, None)
    assert "보류" not in text
    assert "#1~4" in text
    assert "#19~25" in text
    assert "이상점 발생" in text


def test_build_summary_remarks_stable():
    analysis = _make_analysis()
    decision = _minimal_decision(stable=True)
    text = build_summary_remarks(analysis, decision, None)
    assert "R 관리도" in text
    assert "X bar 관리도" in text
    assert "정규" in text


def test_build_summary_dataframe_batch():
    a1 = _make_analysis()
    a2 = _make_analysis(usl=3.0, lsl=0.05)
    d1 = _minimal_decision(stable=True)
    d2 = _minimal_decision(stable=False)

    child1 = SpcPipelineResult(
        characteristic="Point_A",
        split_column="measurement_point",
        analysis=a1,
        decision=d1,
        sample_count=125,
    )
    child2 = SpcPipelineResult(
        characteristic="Point_B",
        split_column="measurement_point",
        analysis=a2,
        decision=d2,
        sample_count=125,
    )
    pipe = SpcPipelineResult(
        split_column="measurement_point",
        split_results=[child1, child2],
        study_info={"process": "Test"},
    )
    df = build_summary_dataframe(pipe)
    assert len(df) == 2
    assert list(df.columns) == SUMMARY_COLUMNS
    assert set(df["판정"]) >= {"안정", "불안정"}


def test_generate_summary_excel_bytes():
    analysis = _make_analysis()
    pipe = SpcPipelineResult(
        characteristic="Single",
        analysis=analysis,
        decision=_minimal_decision(stable=True),
        sample_count=125,
        study_info={"process": "P1"},
    )
    data, fname = generate_summary_excel_bytes(pipe)
    assert fname.endswith(".xlsx")
    assert data[:2] == b"PK"
    assert len(data) > 3000


def test_iter_leaf_nested_batch():
    inner = SpcPipelineResult(characteristic="x", analysis=_make_analysis())
    nested = SpcPipelineResult(split_results=[inner])
    pipe = SpcPipelineResult(split_results=[nested])
    assert len(iter_leaf_pipeline_results(pipe)) == 1
