"""이상점 수집 테스트."""
from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from src.spc.chart_violations import (
    collect_chart_violation_points,
    expand_violation_row_indices,
    violation_measurement_values,
)
from src.spc.decision_models import (
    CompanyChartDecision,
    ControlChartDecision,
    DetectedPattern,
    WesternElectricViolationSummary,
)


def test_collect_from_analysis_ooc():
    analysis = SimpleNamespace(out_of_control_points=[3, 7])
    pts = collect_chart_violation_points(None, analysis)
    assert pts == {3, 7}


def test_collect_from_company_rules():
    analysis = SimpleNamespace(out_of_control_points=[1])
    company = CompanyChartDecision(
        status="비관리상태",
        detected_rules=[{"ruleName": "RUN", "matched_points": [5, 6]}],
        summary_message="",
        actions=[],
    )
    cc = ControlChartDecision(
        is_stable=False,
        status="unstable",
        r_chart_status=None,
        mean_chart_status="unstable",
        detected_patterns=[],
        western_electric_violations=[],
        western_electric_summary="",
        decision_log=[],
        recommendation="",
        company_interpretation=company,
    )
    decision = SimpleNamespace(control_chart=cc)
    pts = collect_chart_violation_points(decision, analysis)
    assert pts == {1, 5, 6}


def test_expand_subgroup_rows():
    df = pd.DataFrame({
        "value": [1.0, 1.1, 2.0, 2.1, 2.2],
        "subgroup_id": [1, 1, 2, 2, 2],
    })
    rows = expand_violation_row_indices(df, {2}, "xbar_r")
    assert rows == {3, 4, 5}
    assert violation_measurement_values(df, {2}, "xbar_r") == [2.0, 2.1, 2.2]


def test_collect_dispersion_points():
    import numpy as np
    from src.spc.chart_violations import collect_dispersion_violation_points
    from src.spc.statistics import SpcAnalyzer

    subgroups = np.array([[1, 2, 3, 4, 5], [1, 2, 3, 4, 50]])
    analysis = SpcAnalyzer().analyze_xbar_s(subgroups, usl=100, lsl=0)
    disp = collect_dispersion_violation_points(analysis)
    assert isinstance(disp, set)


def test_collect_from_patterns_and_we():
    analysis = SimpleNamespace(out_of_control_points=[])
    patterns = [DetectedPattern("p1", "한계이탈", "", [], [], "high", [2, 4])]
    we = [WesternElectricViolationSummary("CO_X", "RUN", 1, [8])]
    cc = ControlChartDecision(
        is_stable=False,
        status="unstable",
        r_chart_status=None,
        mean_chart_status="unstable",
        detected_patterns=patterns,
        western_electric_violations=we,
        western_electric_summary="",
        decision_log=[],
        recommendation="",
        company_interpretation=None,
    )
    decision = SimpleNamespace(control_chart=cc)
    pts = collect_chart_violation_points(decision, analysis)
    assert pts == {2, 4, 8}
