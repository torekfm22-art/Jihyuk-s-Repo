"""이상점 표 테스트."""
from __future__ import annotations

from types import SimpleNamespace

from src.spc.anomaly_point_table import build_anomaly_point_table
from src.spc.decision_models import (
    CompanyChartDecision,
    ControlChartDecision,
    DetectedPattern,
)


def test_anomaly_point_table_from_company_rules():
    company = CompanyChartDecision(
        status="비관리상태",
        detected_rules=[{
            "ruleId": "SHIFT",
            "ruleName": "한쪽 집중 (Shift)",
            "condition": "7점 이상 연속 중심선 한쪽",
            "interpretation": "공정 평균 이동",
            "matched_points": [3, 4, 5],
            "matched_values": [10.05, 10.06, 10.04],
        }],
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
    analysis = SimpleNamespace(chart_type="imr", out_of_control_points=[])
    df = build_anomaly_point_table(decision, analysis)
    assert len(df) == 3
    assert "중심선 한쪽" in df.iloc[0]["조건"]
    assert "공정 평균 이동" in df.iloc[0]["해석 의미"]


def test_validation_comparison_df():
    import numpy as np
    import pandas as pd

    from src.spc.statistics import CapabilityResult, NormalityResult, SpcAnalysisResult
    from src.spc_streamlit.validation_export import build_validation_comparison_df

    vals = np.array([1.0, 1.1, 1.2, 1.3, 1.4])
    cap = CapabilityResult(
        usl=2.0, lsl=0.0, mean=float(vals.mean()), std_within=0.1, std_overall=float(vals.std(ddof=1)),
        cp=1.0, cpk=1.0, pp=1.0, ppk=1.0, cpu=1.0, cpl=1.0, ppm_est=0.0,
    )
    analysis = SpcAnalysisResult(
        chart_type="imr",
        normality=NormalityResult(test_name="Shapiro", statistic=0.9, p_value=0.5, is_normal=True, n=len(vals)),
        control_limits=SimpleNamespace(
            subgroup_size=None, center_line=1.2, sigma_estimate=0.1,
            xbar_limits=None, s_limits=None, r_limits=None,
            i_limits={"CL": 1.2, "UCL": 1.5, "LCL": 0.9},
            mr_limits={"CL": 0.1, "UCL": 0.3},
        ),
        capability=cap,
        individual_stats=pd.DataFrame({"point": range(1, 6), "I": vals, "MR": [np.nan, 0.1, 0.1, 0.1, 0.1]}),
    )
    sample_df = pd.DataFrame({"value": vals})
    df = build_validation_comparison_df(analysis, sample_df)
    assert not df.empty
    assert "구분" in df.columns
    assert (df.loc[df["항목"] == "표본수 n", "구분"] == "표본 통계").any()
    assert (df.loc[df["항목"] == "I UCL", "구분"] == "관리도").any()
    assert (df.loc[df["항목"] == "표본수 n", "일치"] == "OK").any()


def test_validation_comparison_df_xbar_r_limits():
    import numpy as np
    import pandas as pd

    from src.spc.statistics import CapabilityResult, NormalityResult, SpcAnalysisResult
    from src.spc_streamlit.validation_export import build_validation_comparison_df
    from src.spc.constants import A2, D3, D4

    n = 5
    xbar = np.array([10.0, 10.1, 9.9, 10.05, 10.02])
    r_vals = np.array([0.2, 0.15, 0.18, 0.22, 0.17])
    xbar_bar = float(xbar.mean())
    r_bar = float(r_vals.mean())
    sg = pd.DataFrame({"subgroup": range(1, 6), "Xbar": xbar, "R": r_vals})
    vals = np.repeat(xbar, n)
    cap = CapabilityResult(
        usl=12.0, lsl=8.0, mean=float(vals.mean()), std_within=0.05, std_overall=float(vals.std(ddof=1)),
        cp=1.0, cpk=1.0, pp=1.0, ppk=1.0, cpu=1.0, cpl=1.0, ppm_est=0.0,
    )
    analysis = SpcAnalysisResult(
        chart_type="xbar_r",
        normality=NormalityResult(test_name="Shapiro", statistic=0.95, p_value=0.4, is_normal=True, n=len(vals)),
        control_limits=SimpleNamespace(
            subgroup_size=n, center_line=xbar_bar, sigma_estimate=r_bar / 2.326,
            xbar_limits={"CL": xbar_bar, "UCL": xbar_bar + A2[n] * r_bar, "LCL": xbar_bar - A2[n] * r_bar},
            r_limits={"CL": r_bar, "UCL": D4[n] * r_bar, "LCL": D3[n] * r_bar},
            s_limits=None, i_limits=None, mr_limits=None,
        ),
        capability=cap,
        subgroup_stats=sg,
    )
    df = build_validation_comparison_df(analysis, pd.DataFrame({"value": vals}))
    for label in ("Xbar UCL", "Xbar LCL", "R UCL", "R LCL"):
        assert label in df["항목"].values
        assert (df.loc[df["항목"] == label, "구분"] == "관리도").all()
        assert (df.loc[df["항목"] == label, "일치"] == "OK").all()
