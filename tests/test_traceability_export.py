"""Excel 역추적 시트 생성."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd

from src.spc.decision_models import (
    CapabilityDecision,
    CompanyChartDecision,
    ControlChartDecision,
    SpcDecisionResult,
    VerdictSummary,
)
from src.spc.statistics import CapabilityResult, NormalityResult, SpcAnalysisResult
from src.spc.traceability_export import (
    build_subgroup_trace_table,
    build_traceable_sample_dataframe,
    build_traceability_sheets,
)


def _minimal_decision(*, stable: bool = False, capable: bool = False) -> SpcDecisionResult:
    company = CompanyChartDecision(
        status="비관리상태" if not stable else "관리상태",
        detected_rules=[{
            "ruleId": "CONTROL_LIMIT_OUT",
            "ruleName": "관리상한/하한 이탈",
            "condition": "UCL/LCL 벗어남",
            "interpretation": "특수원인",
            "matched_points": [2],
            "matched_values": [10.5],
        }] if not stable else [],
        summary_message="",
        actions=[],
    )
    cc = ControlChartDecision(
        is_stable=stable,
        status="stable" if stable else "unstable",
        r_chart_status=None,
        mean_chart_status="stable" if stable else "unstable",
        detected_patterns=[],
        western_electric_violations=[],
        western_electric_summary="",
        decision_log=[],
        recommendation="",
        company_interpretation=company,
    )
    cap = CapabilityDecision(
        metric_basis="CpCpk",
        primary_kpi="Cpk",
        primary_kpi_value=1.0 if capable else 0.8,
        primary_kpi_label="Cpk=0.80 (Invalid)" if not capable else "Cpk=1.00",
        cp_cpk_valid=stable,
        cp_cpk_validity_note="Valid" if stable else "Invalid",
        cp=1.0, cpk=0.8 if not capable else 1.2,
        pp=1.0, ppk=0.9,
        cpu=None, cpl=None, ppu=None, ppl=None,
        cpk_ppk_gap=0.1,
        gap_interpretation="test",
        process_level="L2",
        is_capable=capable,
        capability_status="insufficient" if not capable else "sufficient",
        improvement_focus="variation" if not capable else "maintain_monitor",
        recommendation="산포 개선",
    )
    return SpcDecisionResult(
        metadata=SimpleNamespace(spec_type="two_sided"),
        control_chart=cc,
        normality=SimpleNamespace(
            test_name="Shapiro", p_value=0.5, is_normal=True, normality_state="normal",
            qqplot_assessment={}, handling_recommendation="", non_normal_detected=False,
            applied_action=None,
        ),
        capability=cap,
        compliance=SimpleNamespace(priority_actions=["조치1"], requires_control_limit_reset=False),
        aiag_vda_extensions=SimpleNamespace(
            pre_control_recommendation="", machine_capability_needed=False,
            machine_capability=SimpleNamespace(message=""),
            pp_ppk_basis_note="", cp_cpk_basis_note="",
            report_completeness=SimpleNamespace(completeness_ok=True, missing_items=[], warnings=[]),
        ),
        expert_commentary=SimpleNamespace(
            executive_summary="", control_chart_comment="", normality_comment="",
            capability_comment="", followup_action_comment="", field_operator_comment="",
        ),
        verdict_summary=VerdictSummary(
            process_stability="Stable" if stable else "Unstable",
            normality_verdict="정규",
            primary_kpi="Cpk",
            cp_cpk_validity="Valid" if stable else "Invalid",
            capability_verdict="부족" if not capable else "충족",
            process_level="L2",
            subgroup_rationality="OK",
            western_electric_summary="",
            control_chart_deploy="",
            priority_action="",
        ),
    )


def test_traceable_sample_flags_spec_and_control():
    vals = [10.0, 10.1, 10.5, 10.2, 10.0] * 5
    sample = pd.DataFrame({
        "value": vals,
        "subgroup_id": [1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3,
                        4, 4, 4, 4, 4, 5, 5, 5, 5, 5],
    })
    sub_stats = pd.DataFrame({
        "subgroup": [1, 2, 3, 4, 5],
        "Xbar": [10.08, 10.12, 10.05, 10.1, 10.08],
        "R": [0.5, 0.4, 0.3, 0.35, 0.4],
    })
    cap = CapabilityResult(
        usl=10.3, lsl=9.5, mean=float(np.mean(vals)), std_within=0.1, std_overall=0.15,
        cp=1.0, cpk=1.0, pp=1.0, ppk=1.0, cpu=1.0, cpl=1.0, ppm_est=0.0,
    )
    analysis = SpcAnalysisResult(
        chart_type="xbar_r",
        normality=NormalityResult("Shapiro", 0.9, 0.5, True, n=len(vals)),
        control_limits=SimpleNamespace(
            subgroup_size=5, xbar_limits={"UCL": 10.25, "LCL": 9.95},
            r_limits={"UCL": 0.45, "LCL": 0.0},
            s_limits=None, i_limits=None, mr_limits=None,
        ),
        capability=cap,
        subgroup_stats=sub_stats,
        out_of_control_points=[2],
    )
    decision = _minimal_decision(stable=False, capable=False)
    traced = build_traceable_sample_dataframe(sample, analysis, decision)
    assert "역추적_주의" in traced.columns
    assert (traced["규격이탈"] == "Y").any()
    assert (traced["관리한계_평균차트"] == "Y").any() or (traced["이상Rule"] == "Y").any()

    sg = build_subgroup_trace_table(sample, analysis, decision)
    assert not sg.empty
    assert (sg["역추적_주의"] == "Y").any()

    sheets = build_traceability_sheets(sample, analysis, decision)
    names = [n for n, _ in sheets]
    assert "역추적_채취표본" in names
    assert "역추적_Subgroup" in names
    assert "역추적_요약" in names
