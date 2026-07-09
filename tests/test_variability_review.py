"""변동성 기반 Worst 이상점 검토 테스트."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd

from src.spc.decision_models import CompanyChartDecision, ControlChartDecision
from src.spc.statistics import CapabilityResult, NormalityResult, SpcAnalysisResult
from src.spc.variability_review import build_variability_review, review_to_dataframe


def _decision_with_rules():
    company = CompanyChartDecision(
        status="비관리상태",
        detected_rules=[
            {
                "ruleId": "EXCESS_DISPERSION",
                "ruleName": "과도 분산",
                "condition": "8점 연속 ±1σ 외부",
                "interpretation": "공정 변동 증가",
                "matched_points": [3, 5],
                "matched_values": [10.1, 10.2],
            },
            {
                "ruleId": "CONTROL_LIMIT_OUT",
                "ruleName": "관리상한/하한 이탈",
                "condition": "UCL 또는 LCL 벗어남",
                "interpretation": "특수원인 발생 (공정 비관리 상태)",
                "matched_points": [5, 7],
                "matched_values": [10.35, 10.36],
            },
        ],
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
    return SimpleNamespace(
        control_chart=cc,
        capability=SimpleNamespace(cpk=0.95, cp_cpk_valid=True, cp_cpk_validity_note="ok"),
        normality=SimpleNamespace(is_normal=True),
    )


def test_chart_distance_beats_rule_stacking():
    """한계 이탈 한 건보다 런+산포 복수 규칙만 있는 점이 높게 나오지 않아야 함."""
    company = CompanyChartDecision(
        status="비관리상태",
        detected_rules=[
            {
                "ruleId": "SHIFT",
                "ruleName": "한쪽 집중 (Shift)",
                "condition": "7점 이상 연속 중심선 한쪽",
                "interpretation": "공정 평균 이동",
                "matched_points": [3, 4, 5, 6, 7, 8, 9],
            },
            {
                "ruleId": "EXCESS_DISPERSION",
                "ruleName": "과도 분산",
                "condition": "8점 연속 ±1σ 외부",
                "interpretation": "공정 변동 증가",
                "matched_points": [5, 6, 7, 8, 9],
            },
            {
                "ruleId": "CONTROL_LIMIT_OUT",
                "ruleName": "관리상한/하한 이탈",
                "condition": "UCL 또는 LCL 벗어남",
                "interpretation": "특수원인 발생 (공정 비관리 상태)",
                "matched_points": [3, 10],
            },
        ],
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
    decision = SimpleNamespace(
        control_chart=cc,
        capability=SimpleNamespace(cpk=1.0, cp_cpk_valid=True, cp_cpk_validity_note="ok"),
        normality=SimpleNamespace(is_normal=True),
    )
    xbars = [10.0] * 9 + [12.5]  # SG10 clearly farthest on chart
    sg = pd.DataFrame({
        "subgroup": range(1, 11),
        "Xbar": xbars,
        "R": [0.5] * 10,
    })
    analysis = SpcAnalysisResult(
        chart_type="xbar_r",
        normality=NormalityResult("Shapiro", 0.9, 0.5, True, n=50),
        control_limits=SimpleNamespace(
            subgroup_size=5,
            center_line=10.0,
            sigma_estimate=0.3,
            xbar_limits={"CL": 10.0, "UCL": 10.9, "LCL": 9.1},
            s_limits=None,
            r_limits={"CL": 0.5, "UCL": 1.0, "LCL": 0.0},
            i_limits=None,
            mr_limits=None,
        ),
        capability=CapabilityResult(
            usl=13.0, lsl=7.0, mean=10.0, std_within=0.3, std_overall=0.3,
            cp=1.0, cpk=1.0, pp=1.0, ppk=1.0, cpu=1.0, cpl=1.0, ppm_est=0.0,
        ),
        subgroup_stats=sg,
        out_of_control_points=[10],
    )
    result = build_variability_review(decision, analysis)
    top = result.reviews[0]
    assert top.point_id == 10, f"expected SG10 on top, got SG{top.point_id}"
    sg7 = next(r for r in result.reviews if r.point_id == 7)
    assert top.variability_score > sg7.variability_score


def test_worst_selection_and_priority():
    vals = np.linspace(1.0, 2.0, 10)
    cap = CapabilityResult(
        usl=3.0, lsl=0.0, mean=float(vals.mean()), std_within=0.2, std_overall=0.2,
        cp=1.0, cpk=0.95, pp=1.0, ppk=0.9, cpu=1.0, cpl=0.9, ppm_est=0.0,
    )
    analysis = SpcAnalysisResult(
        chart_type="imr",
        normality=NormalityResult("Shapiro", 0.9, 0.5, True, n=10),
        control_limits=SimpleNamespace(
            subgroup_size=None, center_line=1.5, sigma_estimate=0.2,
            xbar_limits=None, s_limits=None, r_limits=None,
            i_limits={"CL": 1.5, "UCL": 2.1, "LCL": 0.9},
            mr_limits={"CL": 0.1, "UCL": 0.3},
        ),
        capability=cap,
        individual_stats=pd.DataFrame({
            "point": range(1, 11),
            "I": vals,
            "MR": [np.nan] + [0.1] * 9,
        }),
        out_of_control_points=[7],
    )
    sample_df = pd.DataFrame({
        "value": vals,
        "timestamp": pd.date_range("2026-01-01", periods=10, freq="h"),
    })
    result = build_variability_review(_decision_with_rules(), analysis, sample_df)
    assert len(result.worst) >= 1
    assert result.worst[0].priority == "High"
    assert result.worst[0].variability_summary
    assert result.worst[0].likely_causes
    assert result.worst[0].improvement_actions
    df = review_to_dataframe(result)
    assert "우선순위" in df.columns
    assert "원인 코드" in df.columns
    assert "판정 기준" in df.columns
    assert "이상 사유" in df.columns
    assert (df["우선순위"] == "High").any()
