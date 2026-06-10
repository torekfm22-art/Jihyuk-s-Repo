"""SPC 전문가 해석 코멘트 엔진 (한국어 템플릿 기반)."""
from __future__ import annotations

from src.spc.decision_models import (
    CapabilityDecision,
    ComplianceDecision,
    ControlChartDecision,
    ExpertCommentary,
    NormalityDecision,
    SpcDecisionResult,
    VerdictSummary,
)
from src.spc.policy_config import SpcPolicyConfig
from src.spc.rule_engine import (
    infer_capability_label,
    infer_deploy_label,
    infer_normality_label,
    infer_stability_label,
)


class CommentaryTemplates:
    """한국어 문구 중앙 관리."""

    STABLE_OK = (
        "해석용 관리도 기준으로 공정이 통계적 안정 상태로 판단됩니다. "
        "특별원인 신호가 뚜렷하지 않으므로 현 관리한계선을 유지하며 정기 모니터링을 권장합니다."
    )
    UNSTABLE_R_FIRST = (
        "본 공정은 해석용 관리도 기준으로 안정상태가 확인되지 않았습니다. "
        "특히 산포 관리도에서 이상신호가 확인되어 현재 관리한계선을 기반으로 한 현장 운영은 부적절합니다. "
        "이 경우 평균 위치 해석보다 산포 원인 제거가 우선이며, 공정 안정화 후 재수집 데이터를 기준으로 "
        "관리한계선을 다시 설정해야 합니다."
    )
    UNSTABLE_GENERAL = (
        "관리도에서 이상 패턴 또는 관리한계 이탈이 확인되었습니다. "
        "공정이 안정 상태가 아니므로 현장 관리용 관리도 적용이 제한됩니다. "
        "이탈 시점의 4M1E 변경 이력을 확인하고 원인 제거 후 재수집이 필요합니다."
    )
    CAPABILITY_MAINTAIN = (
        "공정능력 지수가 내부 기준을 충족합니다. "
        "현재 수준을 유지하면서 추이 모니터링과 정기 재평가를 수행하십시오."
    )
    CAPABILITY_CENTERING = (
        "공정 산포(폭)는 기준을 만족하나 중심 지수가 부족합니다. "
        "산포 개선보다 규격 중심 대비 평균 위치 조정(centering)이 우선 과제입니다."
    )
    CAPABILITY_VARIATION = (
        "산포 지수와 중심 지수가 모두 기준 미달입니다. "
        "규격 폭 대비 변동이 크므로 설비·치공구·자재·측정 요인을 점검해 산포를 줄이는 것이 최우선입니다."
    )
    NORM_NORMAL = "정규성 검정과 QQ plot 해석이 정규 가정과 크게 어긋나지 않습니다. Cp/Cpk·Pp/Ppk 해석에 무리가 없습니다."
    NORM_STRICT = (
        "데이터가 정규분포 가정에서 벗어났습니다. "
        "단순 p-value 판정에 그치지 말고 원인을 파악하고 조치한 뒤 데이터를 재수집하여 재분석하십시오."
    )
    NORM_ADVANCED = (
        "비정규 판정입니다. 회사 기준에 따라 원인 파악·조치·재수집을 우선하되, "
        "필요 시 Box-Cox 변환, 비정규 분포 적합, 비모수 공정능력 분석을 검토할 수 있습니다."
    )
    SC_CAPABILITY = (
        "본 항목은 특별특성으로 분류되어 있습니다. 공정능력이 부족하므로 "
        "봉쇄(containment) 검토, 전수검사 전환 검토, 관리계획서·작업표준 반영 검토가 필요합니다."
    )
    SC_UNSTABLE = (
        "특별특성 항목에서 공정 불안정이 확인되었습니다. "
        "관리계획서 개정 필요성과 작업표준 보완을 즉시 검토하십시오."
    )
    CUSTOMER_EXCEPTION = (
        "고객 예외 승인 모드가 적용되었습니다. Cp는 기준을 충족하나 Cpk는 미달이나, "
        "고객이 인지한 예외 조건에 따라 예외적 수용(exception-based acceptance)이 검토됩니다. "
        "예외 판정 사유를 보고서에 명시하고 고객 승인 근거를 유지하십시오."
    )
    FIELD_VARIATION = (
        "이번 결과는 평균이 약간 벗어난 문제라기보다 공정 흔들림이 크다는 의미에 가깝습니다. "
        "먼저 설비 상태, 치공구, 자재, 측정 이상 여부를 점검해 산포를 키우는 원인을 줄이는 것이 우선입니다."
    )
    FIELD_CENTERING = (
        "공정 폭(산포)은 충분하나 평균 위치가 규격 중심에서 벗어났습니다. "
        "셋업값·목표값·공정 중심을 조정하는 것이 가장 빠른 개선 방법입니다."
    )
    FIELD_STABLE = "현재 데이터에서는 특별한 이상 신호가 없습니다. 기존 관리 방식을 유지하며 주기적으로 다시 확인하십시오."


def build_expert_commentary(
    decision: SpcDecisionResult,
    policy: SpcPolicyConfig,
    exception_reason: str | None = None,
) -> ExpertCommentary:
    """전문가 해석 코멘트 생성."""
    ctrl = decision.control_chart
    norm = decision.normality
    cap = decision.capability
    comp = decision.compliance
    meta = decision.metadata

    # 경영진 요약
    exec_parts: list[str] = []
    if ctrl.status == "deferred":
        exec_parts.append(CommentaryTemplates.UNSTABLE_R_FIRST)
    elif ctrl.status == "unstable":
        exec_parts.append(CommentaryTemplates.UNSTABLE_GENERAL)
    else:
        exec_parts.append(CommentaryTemplates.STABLE_OK)

    if cap:
        if cap.improvement_focus == "variation":
            exec_parts.append(CommentaryTemplates.CAPABILITY_VARIATION)
        elif cap.improvement_focus == "centering":
            exec_parts.append(CommentaryTemplates.CAPABILITY_CENTERING)
        elif cap.improvement_focus == "maintain_monitor":
            exec_parts.append(CommentaryTemplates.CAPABILITY_MAINTAIN)

    if meta.special_characteristic:
        if cap and cap.capability_status == "insufficient":
            exec_parts.append(CommentaryTemplates.SC_CAPABILITY)
        if not ctrl.is_stable:
            exec_parts.append(CommentaryTemplates.SC_UNSTABLE)

    if comp.can_deploy_control_chart == "exceptional":
        reason = exception_reason or meta.customer_exception_reason or "고객 승인 예외"
        exec_parts.append(CommentaryTemplates.CUSTOMER_EXCEPTION.replace("예외 판정 사유", f"사유: {reason}"))

    executive = " ".join(exec_parts[:5])

    # 관리도 코멘트
    if ctrl.detected_patterns:
        names = ", ".join(p.pattern_name_ko for p in ctrl.detected_patterns[:3])
        ctrl_comment = (
            f"관리도에서 {names} 등 {len(ctrl.detected_patterns)}건의 이상 패턴이 감지되었습니다. "
            f"{ctrl.recommendation}"
        )
    elif ctrl.is_stable:
        ctrl_comment = "관리한계 내에서 운영되고 있으며, 해석용 관리도 기준 안정 상태입니다."
    else:
        ctrl_comment = ctrl.recommendation

    # 정규성 코멘트
    if norm.normality_state == "normal":
        norm_comment = CommentaryTemplates.NORM_NORMAL
    elif policy.strict_company_mode and not policy.advanced_spc_mode:
        norm_comment = (
            f"{CommentaryTemplates.NORM_STRICT} "
            f"(검정: {norm.test_name}, p={norm.p_value:.4f}, QQ: {norm.qqplot_assessment.get('message', '')})"
        )
    elif policy.advanced_spc_mode:
        norm_comment = CommentaryTemplates.NORM_ADVANCED
    else:
        norm_comment = norm.handling_recommendation

    # 공정능력 코멘트
    cap_parts: list[str] = []
    if meta.stage == "mass_production":
        cap_parts.append("현재 지표는 Cp/Cpk 기준 잠재 공정능력 해석이 중심입니다.")
        if cap and not cap.cp_meaningful:
            cap_parts.append("단측 규격이므로 Cp는 참고하지 않으며 Cpk 중심으로 판정합니다.")
    else:
        cap_parts.append(
            "현재 지표는 Ppk/Pp 기준으로 해석해야 하며, 초기/선행 단계 전체 변동을 반영한 결과입니다."
        )

    if cap:
        if cap.improvement_focus == "centering":
            cap_parts.append(CommentaryTemplates.CAPABILITY_CENTERING)
        elif cap.improvement_focus == "variation":
            cap_parts.append(CommentaryTemplates.CAPABILITY_VARIATION)
        elif cap.improvement_focus == "maintain_monitor":
            cap_parts.append(CommentaryTemplates.CAPABILITY_MAINTAIN)
        if cap.metric_basis == "CpCpk":
            cap_parts.append(f"Cp={cap.cp:.3f}, Cpk={cap.cpk:.3f} (기준 Cp/Cpk≥{policy.cp_cpk_threshold})")
        else:
            cap_parts.append(f"Pp={cap.pp:.3f}, Ppk={cap.ppk:.3f} (기준 Pp/Ppk≥{policy.pp_ppk_threshold})")

    capability_comment = " ".join(cap_parts)

    # 후속조치
    followup_parts = list(comp.priority_actions)
    if comp.requires_control_limit_reset:
        followup_parts.insert(0, "관리한계선 재설정")
    followup_action = (
        "우선 조치: " + " → ".join(dict.fromkeys(followup_parts))
        if followup_parts
        else "추가 조치 없음 — 정기 모니터링"
    )

    # 현장 실무자 코멘트
    if ctrl.status in ("unstable", "deferred"):
        if ctrl.r_chart_status == "unstable":
            field_comment = CommentaryTemplates.FIELD_VARIATION
        else:
            field_comment = CommentaryTemplates.UNSTABLE_GENERAL
    elif cap and cap.improvement_focus == "variation":
        field_comment = CommentaryTemplates.FIELD_VARIATION
    elif cap and cap.improvement_focus == "centering":
        field_comment = CommentaryTemplates.FIELD_CENTERING
    else:
        field_comment = CommentaryTemplates.FIELD_STABLE

    return ExpertCommentary(
        executive_summary=executive,
        control_chart_comment=ctrl_comment,
        normality_comment=norm_comment,
        capability_comment=capability_comment,
        followup_action_comment=followup_action,
        field_operator_comment=field_comment,
    )


def build_verdict_summary(decision: SpcDecisionResult) -> VerdictSummary:
    """자동 판정 요약."""
    ctrl = decision.control_chart
    norm = decision.normality
    cap = decision.capability
    comp = decision.compliance

    priority = comp.priority_actions[0] if comp.priority_actions else "현상 유지"

    return VerdictSummary(
        process_stability=infer_stability_label(ctrl.status),
        normality_verdict=infer_normality_label(norm.normality_state),
        capability_verdict=infer_capability_label(cap.capability_status if cap else "undetermined"),
        control_chart_deploy=infer_deploy_label(comp.can_deploy_control_chart),
        priority_action=priority,
    )
