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
class ControlChartDecision:
    is_stable: bool
    status: StabilityStatus
    r_chart_status: StabilityStatus | None
    mean_chart_status: StabilityStatus | None
    detected_patterns: list[DetectedPattern]
    decision_log: list[DecisionLogEntry]
    recommendation: str

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["detected_patterns"] = [p.to_dict() for p in self.detected_patterns]
        d["decision_log"] = [e.to_dict() for e in self.decision_log]
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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CapabilityDecision:
    metric_basis: Literal["CpCpk", "PpPpk"]
    cp: float | None
    cpk: float | None
    pp: float | None
    ppk: float | None
    cpu: float | None
    cpl: float | None
    ppu: float | None
    ppl: float | None
    is_capable: bool
    capability_status: CapabilityStatus
    improvement_focus: str | None
    recommendation: str
    cp_meaningful: bool = True

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
    capability_verdict: str
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
