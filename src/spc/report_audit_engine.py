"""SPC 리포트 완전성 점검 엔진."""
from __future__ import annotations

from pathlib import Path

from src.spc.decision_models import (
    AiagVdaExtensions,
    MachineCapabilityInfo,
    ReportCompleteness,
)
from src.spc.minitab_charts import ChartPaths
from src.spc.policy_config import SpcPolicyConfig, StageType
from src.spc.qqplot_assessment import calculate_machine_capability
from src.spc.statistics import SpcAnalysisResult


def audit_report_completeness(
    charts: ChartPaths | None,
    analysis: SpcAnalysisResult,
) -> ReportCompleteness:
    """AIAG-VDA Process Capability Study Report 완전성 점검."""
    missing: list[str] = []
    warnings: list[str] = []

    has_histogram = bool(charts and charts.histogram and Path(charts.histogram).exists())
    has_control = bool(charts and charts.control_chart and Path(charts.control_chart).exists())
    has_normality = analysis.normality.n >= 3
    has_capability = analysis.capability is not None

    if charts and charts.prob_plot and not Path(charts.prob_plot).exists():
        warnings.append("정규확률도(QQ plot) 파일 누락 — 정규성 시각 검증 제한")

    if not has_histogram:
        missing.append("histogram")
    if not has_control:
        missing.append("control chart")
    if not has_normality:
        missing.append("normality test")
    if not has_capability:
        missing.append("capability analysis")

    if analysis.normality.n < 3:
        warnings.append("표본수 부족으로 정규성 검정 신뢰도 낮음")

    return ReportCompleteness(
        completeness_ok=len(missing) == 0,
        has_histogram=has_histogram,
        has_control_chart=has_control,
        has_normality_test=has_normality,
        has_capability_analysis=has_capability,
        missing_items=missing,
        warnings=warnings,
    )


def build_aiag_vda_extensions(
    analysis: SpcAnalysisResult,
    charts: ChartPaths | None,
    policy: SpcPolicyConfig,
    stage: StageType,
    subgroup_size: int | None,
    raw_data,
) -> AiagVdaExtensions:
    """AIAG-VDA 개정 요약 반영 확장 필드."""
    completeness = audit_report_completeness(charts, analysis)

    # Pre-control chart recommendation
    if subgroup_size is not None and subgroup_size <= policy.pre_control_subgroup_max:
        pre_control = (
            f"부분군 크기 n={subgroup_size} — Pre-control Chart 운용 검토 가능 "
            f"(AIAG-VDA: 소량·초기 단계 모니터링)"
        )
    elif analysis.chart_type == "imr":
        pre_control = "I-MR 운용 중 — Pre-control Chart 병행 여부 검토"
    else:
        pre_control = "X-bar 계열 운용 — Pre-control Chart는 보조 수단으로 검토"

    machine_needed = stage in policy.machine_capability_recommended_stages  # type: ignore[operator]
    mc_raw = calculate_machine_capability(raw_data, None, None)
    machine_capability = MachineCapabilityInfo(
        supported=mc_raw.get("supported", False),
        message=mc_raw.get("message", ""),
        cm=mc_raw.get("cm"),
        cmk=mc_raw.get("cmk"),
    )

    pp_note = (
        "Pp/Ppk: 전체 변동(σ_overall, ddof=1) 기반 — 개발/선행 단계 평가에 적합"
    )
    cp_note = (
        "Cp/Cpk: 관리도 기반 σ_within 추정 — 양산 단계 잠재 공정능력 평가에 적합"
    )

    return AiagVdaExtensions(
        pre_control_recommendation=pre_control,
        machine_capability_needed=machine_needed,
        machine_capability=machine_capability,
        report_completeness=completeness,
        pp_ppk_basis_note=pp_note,
        cp_cpk_basis_note=cp_note,
    )
