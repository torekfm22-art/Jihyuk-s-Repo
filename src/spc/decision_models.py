"""SPC 판정·해석 통합 결과 모델."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

SpecType = Literal["two_sided", "upper_only", "lower_only"]
DeployStatus = Literal["possible", "not_possible", "exceptional", "undetermined"]
NormalityState = Literal[
    "normal",
    "borderline_non_normal",
    "clearly_non_normal",
    "mixed_distribution_suspected",
    "undetermined",
]
CapabilityStatus = Literal["sufficient", "insufficient", "conditional", "undetermined"]
StabilityStatus = Literal["stable", "unstable", "deferred", "undetermined"]


@dataclass
class DecisionLogEntry:
    rule_id: str
    message: str
    priority: int = 100

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DetectedPattern:
    pattern_id: str
    pattern_name_ko: str
    description: str
    likely_causes: list[str]
    recommended_actions: list[str]
    severity: str
    affected_points: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AnalysisMetadata:
    chart_type: str
    subgroup_size: int | None
    sample_group_count: int
    stage: str
    spec_type: SpecType
    special_characteristic: bool
    customer_exception_mode: bool
    process_change_detected: bool
    customer_exception_reason: str | None = None
    customer_required_control_zone: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CompanyRuleSummary:
    rule_id: str
    rule_name: str
    occurrence_count: int
    affected_subgroups: list[int]
    cause_codes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CompanyChartDecision:
    status: str
    detected_rules: list[dict[str, Any]]
    summary_message: str
    actions: list[str]
    mean_chart_deferred: bool = False
    dispersion_abnormal: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WesternElectricViolationSummary:
    rule_id: str
    rule_name: str
    occurrence_count: int
    affected_subgroups: list[int]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ControlChartDecision:
    is_stable: bool
    status: StabilityStatus
    r_chart_status: StabilityStatus | None
    mean_chart_status: StabilityStatus | None
    detected_patterns: list[DetectedPattern]
    western_electric_violations: list[WesternElectricViolationSummary]
    western_electric_summary: str
    decision_log: list[DecisionLogEntry]
    recommendation: str
    company_interpretation: CompanyChartDecision | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["detected_patterns"] = [p.to_dict() for p in self.detected_patterns]
        d["western_electric_violations"] = [v.to_dict() for v in self.western_electric_violations]
        d["decision_log"] = [e.to_dict() for e in self.decision_log]
        if self.company_interpretation:
            d["company_interpretation"] = self.company_interpretation.to_dict()
        return d


@dataclass
class NormalityDecision:
    test_name: str
    statistic: float
    p_value: float
    is_normal: bool
    normality_state: NormalityState
    qqplot_assessment: dict[str, Any]
    handling_recommendation: str
    non_normal_detected: bool = False
    applied_action: str | None = None
    transform_method: str | None = None
    transform_success: bool = False
    transform_p_value_after: float | None = None
    transform_detail: str | None = None
    transform_attempts: list[dict[str, Any]] = field(default_factory=list)
    transform_summary: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CapabilityDecision:
    metric_basis: Literal["CpCpk", "PpPpk"]
    primary_kpi: str
    primary_kpi_value: float | None
    primary_kpi_label: str
    cp_cpk_valid: bool
    cp_cpk_validity_note: str
    cp: float | None
    cpk: float | None
    pp: float | None
    ppk: float | None
    cpu: float | None
    cpl: float | None
    ppu: float | None
    ppl: float | None
    cpk_ppk_gap: float | None
    gap_interpretation: str
    process_level: str
    is_capable: bool
    capability_status: CapabilityStatus
    improvement_focus: str | None
    recommendation: str
    cp_meaningful: bool = True
    capability_case: str = ""
    analysis_method: str = ""
    analysis_method_rationale: str = ""
    follow_up_priorities: list[str] = field(default_factory=list)
    non_normal_applied: bool = False
    pp_non_normal: float | None = None
    ppk_non_normal: float | None = None
    cp_non_normal: float | None = None
    cpk_non_normal: float | None = None
    normality_transform_method: str | None = None
    capability_on_transformed: bool = False
    cp_raw_reference: float | None = None
    cpk_raw_reference: float | None = None
    pp_raw_reference: float | None = None
    ppk_raw_reference: float | None = None
    cp_reference: float | None = None
    cpk_reference: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ComplianceDecision:
    can_deploy_control_chart: DeployStatus
    requires_recollection: bool
    requires_process_improvement: bool
    requires_control_limit_reset: bool
    requires_control_plan_review: bool
    requires_work_instruction_review: bool
    requires_containment: bool
    requires_100pct_inspection: bool
    requires_customer_exception_review: bool
    priority_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MachineCapabilityInfo:
    supported: bool
    message: str
    cm: float | None = None
    cmk: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReportCompleteness:
    completeness_ok: bool
    has_histogram: bool
    has_control_chart: bool
    has_normality_test: bool
    has_capability_analysis: bool
    missing_items: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AiagVdaExtensions:
    pre_control_recommendation: str
    machine_capability_needed: bool
    machine_capability: MachineCapabilityInfo
    report_completeness: ReportCompleteness
    pp_ppk_basis_note: str
    cp_cpk_basis_note: str

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["machine_capability"] = self.machine_capability.to_dict()
        d["report_completeness"] = self.report_completeness.to_dict()
        return d


@dataclass
class ExpertCommentary:
    executive_summary: str
    control_chart_comment: str
    normality_comment: str
    capability_comment: str
    followup_action_comment: str
    field_operator_comment: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VerdictSummary:
    process_stability: str
    normality_verdict: str
    primary_kpi: str
    cp_cpk_validity: str
    capability_verdict: str
    process_level: str
    subgroup_rationality: str
    western_electric_summary: str
    control_chart_deploy: str
    priority_action: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SpcDecisionResult:
    """통계 분석 + 회사 기준 판정 + 해석 코멘트 통합 결과."""

    metadata: AnalysisMetadata
    control_chart: ControlChartDecision
    normality: NormalityDecision
    capability: CapabilityDecision | None
    compliance: ComplianceDecision
    aiag_vda_extensions: AiagVdaExtensions
    expert_commentary: ExpertCommentary
    verdict_summary: VerdictSummary

    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata.to_dict(),
            "control_chart": self.control_chart.to_dict(),
            "normality": self.normality.to_dict(),
            "capability": self.capability.to_dict() if self.capability else None,
            "compliance": self.compliance.to_dict(),
            "aiag_vda_extensions": self.aiag_vda_extensions.to_dict(),
            "expert_commentary": self.expert_commentary.to_dict(),
            "verdict_summary": self.verdict_summary.to_dict(),
        }
