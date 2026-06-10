"""SPC 판정·해석 통합 서비스 (기존 통계 분석 위 어댑터 레이어)."""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from src.spc.commentary_engine import build_expert_commentary, build_verdict_summary
from src.spc.decision_models import AnalysisMetadata, SpcDecisionResult
from src.spc.minitab_charts import ChartPaths
from src.spc.policy_config import SpcPolicyConfig, StageType
from src.spc.qqplot_assessment import assess_qq_plot
from src.spc.report_audit_engine import build_aiag_vda_extensions
from src.spc.rule_engine import (
    RuleContext,
    build_capability_decision,
    build_compliance_decision,
    build_control_chart_decision,
    build_normality_decision,
    infer_spec_type,
    run_rules,
)
from src.spc.statistics import SpcAnalysisResult


@dataclass
class SpcDecisionInput:
    """판정 엔진 입력."""

    analysis: SpcAnalysisResult
    raw_data: np.ndarray
    stage: StageType = "mass_production"
    special_characteristic: bool = False
    customer_exception_mode: bool = False
    process_change_detected: bool = False
    customer_exception_reason: str | None = None
    customer_required_control_zone: str | None = None
    usl: float | None = None
    lsl: float | None = None
    subgroup_size: int | None = None
    sample_group_count: int | None = None
    charts: ChartPaths | None = None
    policy: SpcPolicyConfig | None = None


def _sample_group_count(analysis: SpcAnalysisResult) -> int:
    if analysis.subgroup_stats is not None:
        return len(analysis.subgroup_stats)
    if analysis.individual_stats is not None:
        return len(analysis.individual_stats)
    return 0


class SpcDecisionService:
    """통계 결과 → 회사 기준 판정 → 해석 코멘트."""

    def __init__(self, policy: SpcPolicyConfig | None = None):
        self.policy = policy or SpcPolicyConfig.from_yaml()

    def evaluate(self, inp: SpcDecisionInput) -> SpcDecisionResult:
        policy = inp.policy or self.policy
        raw = np.asarray(inp.raw_data, dtype=float)
        raw = raw[~np.isnan(raw)]

        spec_type = infer_spec_type(inp.usl, inp.lsl)  # type: ignore[assignment]
        sg_count = inp.sample_group_count or _sample_group_count(inp.analysis)
        sg_size = inp.subgroup_size or inp.analysis.control_limits.subgroup_size

        metadata = AnalysisMetadata(
            chart_type=inp.analysis.chart_type,
            subgroup_size=sg_size,
            sample_group_count=sg_count,
            stage=inp.stage,
            spec_type=spec_type,  # type: ignore[arg-type]
            special_characteristic=inp.special_characteristic,
            customer_exception_mode=inp.customer_exception_mode,
            process_change_detected=inp.process_change_detected,
            customer_exception_reason=inp.customer_exception_reason,
            customer_required_control_zone=inp.customer_required_control_zone,
        )

        qq = assess_qq_plot(raw)
        ctx = RuleContext(
            analysis=inp.analysis,
            policy=policy,
            metadata=metadata,
            raw_data=raw,
            qq_assessment=qq,
        )
        state = run_rules(ctx)

        control = build_control_chart_decision(state)
        normality = build_normality_decision(inp.analysis.normality, qq, state, policy)
        capability = build_capability_decision(inp.analysis.capability, state, metadata)
        compliance = build_compliance_decision(state)
        aiag = build_aiag_vda_extensions(
            inp.analysis,
            inp.charts,
            policy,
            inp.stage,
            sg_size,
            raw,
        )

        from src.spc.decision_models import ExpertCommentary, VerdictSummary

        partial = SpcDecisionResult(
            metadata=metadata,
            control_chart=control,
            normality=normality,
            capability=capability,
            compliance=compliance,
            aiag_vda_extensions=aiag,
            expert_commentary=ExpertCommentary("", "", "", "", "", ""),
            verdict_summary=VerdictSummary("", "", "", "", ""),
        )
        commentary = build_expert_commentary(
            partial,
            policy,
            state.get("exception_reason"),
        )
        with_commentary = replace(partial, expert_commentary=commentary)
        verdict = build_verdict_summary(with_commentary)

        return replace(with_commentary, verdict_summary=verdict)
