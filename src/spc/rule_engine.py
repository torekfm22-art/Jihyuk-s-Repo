"""SPC 회사 기준 판정 규칙 엔진."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from src.spc.decision_models import (
    AnalysisMetadata,
    CapabilityDecision,
    CapabilityStatus,
    CompanyChartDecision,
    CompanyRuleSummary,
    ComplianceDecision,
    ControlChartDecision,
    DecisionLogEntry,
    DeployStatus,
    DetectedPattern,
    NormalityDecision,
    NormalityState,
    StabilityStatus,
    WesternElectricViolationSummary,
)
from src.spc.capability_strategy import determine_capability_strategy
from src.spc.non_normal_capability import percentile_capability
from src.spc.normality_transform import resolve_normality_transform
from src.spc.pattern_catalog import PATTERN_CATALOG, get_pattern_meta
from src.spc.policy_config import SpcPolicyConfig, StageType
from src.spc.qqplot_assessment import QqPlotAssessment, assess_qq_plot
from src.spc.statistics import (
    CapabilityResult,
    NormalityResult,
    SpcAnalysisResult,
    SpcAnalyzer,
    infer_spec_type,
)
from src.spc.subgroup_rationality import SubgroupRationalityResult, validate_subgroup_rationality
from src.spc.spc_interpreter import (
    CompanyChartInterpretation,
    DetectedCompanyRule,
    format_company_rules_summary,
    interpret_control_chart,
)


@dataclass
class RuleContext:
    """규칙 평가 컨텍스트."""

    analysis: SpcAnalysisResult
    policy: SpcPolicyConfig
    metadata: AnalysisMetadata
    raw_data: np.ndarray
    qq_assessment: QqPlotAssessment | None = None
    sample_df: pd.DataFrame | None = None
    subgroup_rationality: SubgroupRationalityResult | None = None


@dataclass
class Rule:
    id: str
    condition: Callable[[RuleContext, dict], bool]
    action: Callable[[RuleContext, dict], None]
    priority: int = 100


def _meta_to_pattern(pattern_id: str, points: list[int] | None = None) -> DetectedPattern:
    meta = get_pattern_meta(pattern_id)
    if meta is None:
        raise KeyError(pattern_id)
    return DetectedPattern(
        pattern_id=meta.pattern_id,
        pattern_name_ko=meta.pattern_name_ko,
        description=meta.description,
        likely_causes=list(meta.likely_causes),
        recommended_actions=list(meta.recommended_actions),
        severity=meta.severity,
        affected_points=points or [],
    )


def _get_mean_chart_values(ctx: RuleContext) -> tuple[np.ndarray, float, float, float, list[int]]:
    """평균(또는 I) 차트 값, CL, UCL, LCL, 포인트 번호."""
    result = ctx.analysis
    cl = result.control_limits

    if result.chart_type == "imr" and result.individual_stats is not None:
        df = result.individual_stats
        values = df["I"].to_numpy(dtype=float)
        limits = cl.i_limits or {}
        points = df["point"].astype(int).tolist()
    elif result.subgroup_stats is not None:
        df = result.subgroup_stats
        values = df["Xbar"].to_numpy(dtype=float)
        limits = cl.xbar_limits or {}
        points = df["subgroup"].astype(int).tolist()
    else:
        return np.array([]), 0.0, 0.0, 0.0, []

    return (
        values,
        float(limits.get("CL", 0.0)),
        float(limits.get("UCL", 0.0)),
        float(limits.get("LCL", 0.0)),
        points,
    )


def _get_dispersion_ooc_points(ctx: RuleContext) -> list[int]:
    """R/S/MR 차트 UCL 초과 포인트."""
    result = ctx.analysis
    cl = result.control_limits
    ooc: list[int] = []

    if result.chart_type == "imr" and result.individual_stats is not None and cl.mr_limits:
        df = result.individual_stats
        ucl = cl.mr_limits["UCL"]
        for i, v in enumerate(df["MR"].to_numpy()):
            if not np.isnan(v) and v > ucl:
                ooc.append(int(df["point"].iloc[i]))
        return ooc

    df = result.subgroup_stats
    if df is None:
        return ooc

    if result.chart_type == "xbar_r" and cl.r_limits and "R" in df.columns:
        ucl = cl.r_limits["UCL"]
        for i, v in enumerate(df["R"].to_numpy()):
            if v > ucl:
                ooc.append(int(df["subgroup"].iloc[i]))
    elif result.chart_type == "xbar_s" and cl.s_limits and "S" in df.columns:
        ucl = cl.s_limits["UCL"]
        for i, v in enumerate(df["S"].to_numpy()):
            if v > ucl:
                ooc.append(int(df["subgroup"].iloc[i]))
    return ooc


def _company_rule_to_pattern(rule: DetectedCompanyRule) -> DetectedPattern:
    critical_ids = {"SPEC_LIMIT_OUT", "CONTROL_LIMIT_OUT", "OSCILLATION"}
    severity = "critical" if rule.rule_id in critical_ids else "high"
    return DetectedPattern(
        pattern_id=f"company_{rule.rule_id.lower()}",
        pattern_name_ko=rule.rule_name,
        description=f"{rule.condition} → {rule.interpretation_meaning}",
        likely_causes=[rule.interpretation_meaning],
        recommended_actions=[],
        severity=severity,
        affected_points=rule.matched_points,
    )


def _company_rule_to_we_summary(rule: DetectedCompanyRule) -> WesternElectricViolationSummary:
    return WesternElectricViolationSummary(
        rule_id=f"CO_{rule.rule_id}",
        rule_name=rule.rule_name,
        occurrence_count=len(rule.windows) or len(rule.matched_points),
        affected_subgroups=rule.matched_points,
    )



def detect_control_patterns(ctx: RuleContext) -> tuple[list[DetectedPattern], list, CompanyChartInterpretation | None]:
    """관리도 이상 패턴 감지 (회사 표준 — 첨부#2)."""
    patterns: list[DetectedPattern] = []
    we_violations: list[WesternElectricViolationSummary] = []
    policy = ctx.policy
    values, cl, ucl, lcl, point_ids = _get_mean_chart_values(ctx)
    disp_ooc = _get_dispersion_ooc_points(ctx)
    dispersion_abnormal = bool(disp_ooc)

    cap = ctx.analysis.capability
    usl = cap.usl if cap else None
    lsl = cap.lsl if cap else None

    company_interp: CompanyChartInterpretation | None = None
    if len(values) > 0 and ucl != lcl:
        company_interp = interpret_control_chart(
            values, cl, ucl, lcl, point_ids,
            usl=usl,
            lsl=lsl,
            config=policy.interpret_config(),
            dispersion_abnormal=dispersion_abnormal,
        )
        for rule in company_interp.detected_rules:
            patterns.append(_company_rule_to_pattern(rule))
            we_violations.append(_company_rule_to_we_summary(rule))

    seen: set[str] = set()
    unique: list[DetectedPattern] = []
    for p in patterns:
        if p.pattern_id not in seen:
            seen.add(p.pattern_id)
            unique.append(p)
    return unique, we_violations, company_interp


def classify_normality_state(
    norm: NormalityResult,
    qq: QqPlotAssessment,
    policy: SpcPolicyConfig,
) -> NormalityState:
    if norm.n < 3:
        return "undetermined"
    if qq.state_hint == "undetermined":
        return "undetermined"
    if norm.is_normal and qq.state_hint == "normal":
        return "normal"
    if norm.is_normal and norm.p_value >= policy.normality_borderline_p:
        if qq.state_hint == "borderline_non_normal":
            return "borderline_non_normal"
        if qq.state_hint == "clearly_non_normal":
            if qq.fit_r2 is not None and qq.fit_r2 < 0.93:
                return "mixed_distribution_suspected"
            return "borderline_non_normal"
        return "normal"
    if norm.p_value >= policy.normality_borderline_p and qq.state_hint == "borderline_non_normal":
        return "borderline_non_normal"
    if qq.state_hint == "mixed_distribution_suspected":
        return "mixed_distribution_suspected"
    if not norm.is_normal or norm.p_value < policy.normality_clearly_non_normal_p:
        if qq.fit_r2 is not None and norm.is_normal and qq.fit_r2 < 0.93:
            return "mixed_distribution_suspected"
        return "clearly_non_normal" if norm.p_value < policy.normality_borderline_p else "borderline_non_normal"
    return "borderline_non_normal"


def _log(state: dict, rule_id: str, message: str, priority: int = 100) -> None:
    state.setdefault("decision_log", []).append(
        DecisionLogEntry(rule_id=rule_id, message=message, priority=priority)
    )


def _nan_none(value: float | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, float) and (np.isnan(value) or np.isinf(value)):
        return None
    return value


def _rule_data_collection(ctx: RuleContext, state: dict) -> None:
    n_groups = ctx.metadata.sample_group_count
    if n_groups < ctx.policy.subgroup_min_groups:
        _log(
            state,
            "DATA_MIN_GROUPS",
            f"subgroup count={n_groups} < minimum {ctx.policy.subgroup_min_groups} -> interpretation reliability reduced",
            10,
        )
        state["requires_recollection"] = True

    sg = ctx.metadata.subgroup_size
    if sg and sg not in ctx.policy.recommended_subgroup_sizes:
        _log(
            state,
            "DATA_SUBGROUP_SIZE",
            f"subgroup_size={sg} not in recommended {ctx.policy.recommended_subgroup_sizes}",
            50,
        )


def _rule_process_change(ctx: RuleContext, state: dict) -> None:
    if ctx.metadata.process_change_detected:
        _log(
            state,
            "PROCESS_CHANGE",
            "process change detected -> exclude pre-change data, recollect, reset control limits",
            5,
        )
        state["requires_recollection"] = True
        state["requires_control_limit_reset"] = True


def _rule_r_chart_first(ctx: RuleContext, state: dict) -> None:
    if ctx.analysis.chart_type != "xbar_r":
        return

    disp_ooc = _get_dispersion_ooc_points(ctx)
    if disp_ooc:
        state["r_chart_status"] = "unstable"
        state["mean_chart_status"] = "deferred"
        _log(
            state,
            "R_CHART_FIRST",
            "R chart unstable -> mean chart interpretation deferred",
            5,
        )
        state["is_stable"] = False
        state["can_deploy_control_chart"] = "not_possible"
    else:
        state["r_chart_status"] = "stable"


def _rule_dispersion_stability(ctx: RuleContext, state: dict) -> None:
    if ctx.analysis.chart_type == "xbar_s":
        disp_ooc = _get_dispersion_ooc_points(ctx)
        if disp_ooc:
            state.setdefault("r_chart_status", "unstable")
            _log(state, "S_CHART_UNSTABLE", "S chart UCL violation -> dispersion unstable", 8)
            state["is_stable"] = False

    if ctx.analysis.chart_type == "imr":
        disp_ooc = _get_dispersion_ooc_points(ctx)
        if disp_ooc:
            state["r_chart_status"] = "unstable"
            _log(state, "MR_CHART_UNSTABLE", "MR chart UCL violation -> variation unstable", 8)
            state["is_stable"] = False


def _rule_mean_chart_stability(ctx: RuleContext, state: dict) -> None:
    if state.get("mean_chart_status") == "deferred":
        return

    patterns = state.get("detected_patterns", [])
    critical = _has_stability_breaking_signal(patterns, ctx.analysis.out_of_control_points)

    if critical:
        state["mean_chart_status"] = "unstable"
        state["is_stable"] = False
        if state.get("can_deploy_control_chart") != "not_possible":
            state["can_deploy_control_chart"] = "not_possible"
    elif state.get("mean_chart_status") is None:
        state["mean_chart_status"] = "stable"


def _rule_subgroup_rationality(ctx: RuleContext, state: dict) -> None:
    """Rational subgroup 검증."""
    if ctx.subgroup_rationality is None:
        ctx.subgroup_rationality = validate_subgroup_rationality(
            ctx.sample_df,
            subgroup_size=ctx.metadata.subgroup_size,
        )
    result = ctx.subgroup_rationality
    state["subgroup_rationality"] = result
    state["subgroup_rationality_ok"] = result.is_rational
    if not result.is_rational:
        _log(
            state,
            "SUBGROUP_RATIONALITY",
            f"{result.summary_label()} — " + "; ".join(result.violations[:3]),
            7,
        )
        state["requires_recollection"] = True


def _rule_normality_transform(ctx: RuleContext, state: dict) -> None:
    """비정규 데이터 — Box-Cox → Johnson 순 변환 후 정규성·공정능력 재평가."""
    norm_state = state.get("normality_state")
    norm = ctx.analysis.normality
    cap = ctx.analysis.capability

    if norm_state in ("normal", "undetermined"):
        state["normality_action"] = None
        state["non_normal_detected"] = False
        state["normality_transform_applied"] = False
        return

    if norm_state == "borderline_non_normal" and norm.is_normal:
        state["normality_action"] = None
        state["non_normal_detected"] = False
        state["normality_transform_applied"] = False
        _log(
            state,
            "NORMality_BORDERLINE",
            "Shapiro-Wilk 정규 + QQ plot 경계 — 히스토그램·QQ plot 교차 확인 권고",
            22,
        )
        return

    state["non_normal_detected"] = True
    if cap is None or (cap.usl is None and cap.lsl is None):
        state["normality_action"] = "Non-normal → USL/LSL 미지정, Ppk 중심 평가"
        _log(state, "NORMality_ACTION", state["normality_action"], 22)
        return

    t_result = resolve_normality_transform(
        ctx.raw_data,
        cap.usl,
        cap.lsl,
        chart_type=ctx.analysis.chart_type,
        subgroup_size=ctx.metadata.subgroup_size,
        alpha=ctx.policy.normality_borderline_p,
    )
    state["normality_transform_result"] = t_result

    if t_result.applied and t_result.capability is not None:
        state["normality_transform_applied"] = True
        state["transformed_capability"] = t_result.capability
        state["normality_transform_method"] = t_result.method
        method_label = "Box-Cox" if t_result.method == "box_cox" else "Johnson SU"
        lam_note = f", λ={t_result.lambda_:.4f}" if t_result.lambda_ is not None else ""
        state["normality_action"] = (
            f"Non-normal → {method_label} 변환 적용{lam_note} → "
            f"정규성 확보 (p={t_result.normality_after.p_value:.4f}) → "
            f"변환 공간 Cp/Cpk 재평가 (Cpk={t_result.capability.cpk:.3f})"
        )
        _log(
            state,
            "NORMality_TRANSFORM",
            state["normality_action"],
            20,
        )
        return

    state["normality_transform_applied"] = False
    state["normality_action"] = t_result.notes or "Non-normal → Ppk/Non-normal capability 중심 평가"
    if t_result.method == "none" and "Johnson" in (t_result.notes or ""):
        state["johnson_recommended"] = True
    _log(state, "NORMality_ACTION", state["normality_action"], 22)


def _is_process_stable_for_capability(state: dict) -> bool:
    """Cp/Cpk 유효성 판단용 안정 상태 (R-chart-first 포함)."""
    if not state.get("is_stable", False):
        return False
    if state.get("r_chart_status") == "unstable":
        return False
    if state.get("mean_chart_status") == "deferred":
        return False
    return True


def _evaluate_cp_cpk_validity(ctx: RuleContext, state: dict) -> bool:
    """Cp/Cpk 유효 조건: 안정 + 정규성 + rational subgroup + 동일 공정 조건."""
    stable = _is_process_stable_for_capability(state)
    norm_state = state.get("normality_state")
    norm_ok = norm_state == "normal" or state.get("normality_transform_applied", False)
    subgroup_ok = state.get("subgroup_rationality_ok", True)
    process_ok = not ctx.metadata.process_change_detected

    reasons: list[str] = []
    if not stable:
        reasons.append("관리도 불안정")
    if not norm_ok:
        reasons.append("정규성 미충족")
    if not subgroup_ok:
        reasons.append("Non-rational subgroup")
    if not process_ok:
        reasons.append("공정 조건 변경")

    state["cp_cpk_valid"] = len(reasons) == 0
    state["cp_cpk_invalid_reasons"] = reasons
    return state["cp_cpk_valid"]


def _rule_stage_capability(ctx: RuleContext, state: dict) -> None:
    """안정성 우선 공정능력/성능 평가 — Stable→Cp/Cpk, Unstable→Ppk."""
    cap = ctx.analysis.capability
    if cap is None:
        state["capability_status"] = "undetermined"
        _log(state, "CAPABILITY_MISSING", "capability not calculated -> undetermined", 20)
        return

    stable = _is_process_stable_for_capability(state)
    cp_cpk_valid = _evaluate_cp_cpk_validity(ctx, state)
    stage = ctx.metadata.stage
    width_th, center_th = ctx.policy.capability_thresholds(stage)  # type: ignore[arg-type]

    eval_cap = cap
    t_cap = state.get("transformed_capability")
    transform_ok = state.get("normality_transform_applied", False)
    if t_cap is not None and transform_ok:
        eval_cap = t_cap
        state["capability_on_transformed"] = True
        state["cp_raw_reference"] = cap.cp
        state["cpk_raw_reference"] = cap.cpk
        state["pp_raw_reference"] = cap.pp
        state["ppk_raw_reference"] = cap.ppk

    cpk_v = _nan_none(eval_cap.cpk)
    ppk_v = _nan_none(eval_cap.ppk)
    gap = (cpk_v - ppk_v) if cpk_v is not None and ppk_v is not None else None
    state["cpk_ppk_gap"] = gap
    if gap is not None and gap > 0.10:
        state["gap_interpretation"] = "공정 불안정 또는 장기 변동 존재"
    else:
        state["gap_interpretation"] = "공정 안정"

    cp_meaningful = ctx.metadata.spec_type == "two_sided"
    state["cp_meaningful"] = cp_meaningful

    if stable and cp_cpk_valid and stage == "mass_production":
        basis = "CpCpk"
        primary_kpi = "Cpk"
        width_val, center_val = eval_cap.cp, eval_cap.cpk
        width_name, center_name = "Cp", "Cpk"
        if state.get("capability_on_transformed"):
            method = state.get("normality_transform_method", "")
            label = "Box-Cox" if method == "box_cox" else "Johnson SU"
            validity_note = f"Valid ({label} 변환 후 Cp/Cpk)"
        else:
            validity_note = "Valid"
        _log(
            state,
            "STABILITY_CAPABILITY",
            "process stable → Cp/Cpk evaluation (VALID)",
            30,
        )
    elif stable and stage != "mass_production":
        basis = "PpPpk"
        primary_kpi = "Ppk"
        width_val, center_val = eval_cap.pp, eval_cap.ppk
        width_name, center_name = "Pp", "Ppk"
        validity_note = "Valid (stage uses Pp/Ppk)" if cp_cpk_valid else "Invalid — stage Pp/Ppk primary"
        _log(
            state,
            "STAGE_CAPABILITY",
            f"stage={stage} → Pp/Ppk rule (threshold width={width_th}, center={center_th})",
            30,
        )
    else:
        basis = "PpPpk"
        primary_kpi = "Ppk"
        width_val, center_val = eval_cap.pp, eval_cap.ppk
        width_name, center_name = "Pp", "Ppk"
        reasons = state.get("cp_cpk_invalid_reasons", ["관리도 불안정"])
        validity_note = f"Invalid — {reasons[0]}"
        _log(
            state,
            "UNSTABLE_PERFORMANCE",
            f"process not stable or Cp/Cpk invalid → Ppk-centered evaluation; "
            f"Cp/Cpk reference only ({', '.join(reasons)})",
            12,
        )

    state["metric_basis"] = basis
    state["primary_kpi"] = primary_kpi
    state["primary_kpi_value"] = center_val
    state["cp_cpk_validity_note"] = validity_note

    if not cp_meaningful:
        _log(state, "ONE_SIDED_SPEC", "one-sided spec -> Cp/Pp not meaningful, evaluate Cpk/Ppk only", 25)

    width_ok = width_val >= width_th if cp_meaningful else True
    center_ok = center_val >= center_th

    if center_ok and (width_ok or not cp_meaningful):
        state["capability_status"] = "sufficient"
        state["improvement_focus"] = "maintain_monitor"
        _log(state, "CAPABILITY_SUFFICIENT", f"{center_name}>={center_th} -> maintain and monitor", 40)
    elif width_ok and not center_ok:
        state["capability_status"] = "insufficient"
        state["improvement_focus"] = "centering"
        _log(
            state,
            "CAPABILITY_CENTERING",
            f"{width_name}>={width_th} and {center_name}<{center_th} -> centering improvement recommended",
            15,
        )
        state["requires_process_improvement"] = True
    elif not width_ok and not center_ok:
        state["capability_status"] = "insufficient"
        state["improvement_focus"] = "variation"
        _log(
            state,
            "CAPABILITY_VARIATION",
            f"{width_name}<{width_th} and {center_name}<{center_th} -> variation improvement recommended",
            15,
        )
        state["requires_process_improvement"] = True
    else:
        state["capability_status"] = "conditional"
        state["improvement_focus"] = "review"

    state["is_capable"] = state["capability_status"] == "sufficient"

    if not stable:
        state["process_level"] = "Level 1: Unstable (관리도 NG)"
    elif state["is_capable"]:
        state["process_level"] = "Level 3: Stable and Capable (Cpk ≥ 기준)" if primary_kpi == "Cpk" else "Level 3: Stable and Capable (Ppk ≥ 기준)"
    else:
        state["process_level"] = "Level 2: Stable but Incapable (Cpk < 기준)" if primary_kpi == "Cpk" else "Level 2: Stable but Incapable (Ppk < 기준)"

    _apply_capability_strategy(ctx, state, cap, stable)


def _apply_capability_strategy(ctx: RuleContext, state: dict, cap, stable: bool) -> None:
    """Case 1~4 분기 및 Non-normal capability 적용."""
    norm_state = state.get("normality_state", "undetermined")
    transform_ok = state.get("normality_transform_applied", False)
    is_normal = norm_state == "normal" or transform_ok
    boxcox_ok = state.get("normality_transform_method") == "box_cox" and transform_ok
    johnson_ok = state.get("normality_transform_method") == "johnson_su" and transform_ok
    severe = norm_state in ("clearly_non_normal", "mixed_distribution_suspected")

    strategy = determine_capability_strategy(
        stable,
        is_normal,
        boxcox_success=boxcox_ok,
        johnson_success=johnson_ok,
        severe_non_normal=severe and not transform_ok,
    )
    state["capability_case"] = strategy.case_label
    state["analysis_method"] = strategy.primary_method
    state["analysis_method_rationale"] = strategy.method_rationale
    state["follow_up_priorities"] = strategy.follow_up_priorities

    if transform_ok and stable:
        method = state.get("normality_transform_method", "")
        label = "Box-Cox" if method == "box_cox" else "Johnson SU"
        state["analysis_method"] = f"{label} 변환 후 Cp/Cpk"
        state["capability_case"] = f"안정 + {label} 변환 후 정규"
        return

    if not strategy.use_non_normal:
        return

    within_spread = None
    if stable and cap.std_within > 0:
        within_spread = cap.std_within * 6.0

    nn = percentile_capability(
        ctx.raw_data,
        cap.usl,
        cap.lsl,
        within_spread=within_spread if stable else None,
    )
    state["non_normal_capability"] = nn.to_dict()
    state["non_normal_applied"] = True

    if strategy.metric_basis == "CpCpk":
        state["metric_basis"] = "CpCpk"
        state["primary_kpi"] = "Cpk"
        state["primary_kpi_value"] = nn.cpk
        state["analysis_method"] = "Non-normal Cp/Cpk"
        _log(
            state,
            "NON_NORMAL_CP_CPK",
            f"Case 2 → Non-normal Cp/Cpk: Cpk_nn={nn.cpk:.3f}, Cp_nn={nn.cp:.3f}",
            28,
        )
    else:
        state["metric_basis"] = "PpPpk"
        state["primary_kpi"] = "Ppk"
        state["primary_kpi_value"] = nn.ppk
        state["analysis_method"] = "Non-normal Pp/Ppk (percentile)"
        _log(
            state,
            "NON_NORMAL_PP_PPK",
            f"Case 4 → Non-normal Pp/Ppk: Ppk_nn={nn.ppk:.3f}, Pp_nn={nn.pp:.3f}",
            28,
        )

    if strategy.transform_recommendation:
        state["normality_action"] = (
            (state.get("normality_action") or "")
            + f" | 후속: {strategy.transform_recommendation}"
        ).strip(" |")


def _rule_customer_exception(ctx: RuleContext, state: dict) -> None:
    if not ctx.policy.enable_customer_exception_rule:
        return
    if not ctx.metadata.customer_exception_mode:
        return

    cap = ctx.analysis.capability
    if cap is None or ctx.metadata.stage != "mass_production":
        return

    th = ctx.policy.cp_cpk_threshold
    if cap.cp >= th and cap.cpk < th:
        state["can_deploy_control_chart"] = "exceptional"
        state["capability_status"] = "conditional"
        reason = ctx.metadata.customer_exception_reason or "customer approved exception"
        _log(
            state,
            "CUSTOMER_EXCEPTION",
            f"exception-based acceptance: Cp>={th}, Cpk<{th}, reason={reason}",
            12,
        )
        state["requires_customer_exception_review"] = True
        state["exception_reason"] = reason


def _rule_special_characteristic(ctx: RuleContext, state: dict) -> None:
    if not ctx.metadata.special_characteristic:
        return

    _log(state, "SPECIAL_CHARACTERISTIC", "special_characteristic=True -> enhanced control requirements", 18)

    if state.get("capability_status") == "insufficient":
        state["requires_containment"] = True
        state["requires_100pct_inspection"] = True
        state["requires_control_plan_review"] = True
        _log(
            state,
            "SC_CAPABILITY",
            "special characteristic + insufficient capability -> containment/100% inspection/control plan review",
            8,
        )

    if not state.get("is_stable", True):
        state["requires_control_plan_review"] = True
        state["requires_work_instruction_review"] = True
        _log(
            state,
            "SC_UNSTABLE",
            "special characteristic + unstable process -> control plan and work instruction review",
            8,
        )


def _rule_normality_strict(ctx: RuleContext, state: dict) -> None:
    norm_state = state.get("normality_state")
    if norm_state in ("clearly_non_normal", "mixed_distribution_suspected", "borderline_non_normal"):
        if ctx.policy.strict_company_mode and norm_state != "borderline_non_normal":
            state["requires_recollection"] = True
            _log(
                state,
                "NORMality_STRICT",
                "strict_company_mode + non-normal -> cause analysis, action, recollection required",
                14,
            )
        elif norm_state == "borderline_non_normal":
            _log(state, "NORMality_BORDERLINE", "borderline non-normal -> confirm with QQ plot and histogram", 35)


def _rule_deploy_control_chart(ctx: RuleContext, state: dict) -> None:
    if state.get("can_deploy_control_chart") == "exceptional":
        return
    if not state.get("is_stable", True):
        state["can_deploy_control_chart"] = "not_possible"
        _log(
            state,
            "DEPLOY_BLOCKED",
            "process not in stable state -> operational control chart deployment not allowed",
            6,
        )
    elif state.get("can_deploy_control_chart") is None:
        state["can_deploy_control_chart"] = "possible"


RULES: list[Rule] = [
    Rule("DATA_COLLECTION", lambda c, s: True, _rule_data_collection, 10),
    Rule("PROCESS_CHANGE", lambda c, s: c.metadata.process_change_detected, _rule_process_change, 5),
    Rule("SUBGROUP_RATIONALITY", lambda c, s: c.sample_df is not None, _rule_subgroup_rationality, 7),
    Rule("R_CHART_FIRST", lambda c, s: c.analysis.chart_type == "xbar_r", _rule_r_chart_first, 5),
    Rule("DISPERSION_STABILITY", lambda c, s: c.analysis.chart_type in ("xbar_s", "imr"), _rule_dispersion_stability, 8),
    Rule("MEAN_CHART_STABILITY", lambda c, s: True, _rule_mean_chart_stability, 10),
    Rule("NORMALITY_TRANSFORM", lambda c, s: True, _rule_normality_transform, 22),
    Rule("STAGE_CAPABILITY", lambda c, s: True, _rule_stage_capability, 15),
    Rule("SPECIAL_CHARACTERISTIC", lambda c, s: c.metadata.special_characteristic, _rule_special_characteristic, 18),
    Rule("CUSTOMER_EXCEPTION", lambda c, s: c.metadata.customer_exception_mode, _rule_customer_exception, 20),
    Rule("NORMALITY_STRICT", lambda c, s: True, _rule_normality_strict, 14),
    Rule("DEPLOY_CONTROL_CHART", lambda c, s: True, _rule_deploy_control_chart, 6),
]


def _has_stability_breaking_signal(
    patterns: list[DetectedPattern],
    ooc: list[int],
    we_violations: list | None = None,
    company_interp: CompanyChartInterpretation | None = None,
) -> bool:
    """안정성 판정: 회사 표준 이상, OOC, 산포 이탈."""
    if company_interp and company_interp.status == "비관리상태":
        return True
    if we_violations:
        return True
    if ooc:
        return True
    return any(
        p.severity in ("critical", "high")
        or p.pattern_id.startswith("company_")
        for p in patterns
    )


def evaluate_control_chart(ctx: RuleContext) -> tuple[list[DetectedPattern], dict]:
    """관리도 패턴 감지 및 안정성 초기 상태."""
    patterns, we_violations, company_interp = detect_control_patterns(ctx)
    ooc = ctx.analysis.out_of_control_points
    disp_ooc = _get_dispersion_ooc_points(ctx)
    unstable = _has_stability_breaking_signal(
        patterns, ooc, we_violations, company_interp
    ) or bool(disp_ooc)

    summary = (
        format_company_rules_summary(company_interp)
        if company_interp
        else "회사 표준: 데이터 없음"
    )

    state: dict = {
        "detected_patterns": patterns,
        "western_electric_violations": we_violations,
        "western_electric_summary": summary,
        "company_interpretation": company_interp,
        "is_stable": not unstable,
        "decision_log": [],
        "requires_recollection": False,
        "requires_process_improvement": False,
        "requires_control_limit_reset": False,
        "requires_control_plan_review": False,
        "requires_work_instruction_review": False,
        "requires_containment": False,
        "requires_100pct_inspection": False,
        "requires_customer_exception_review": False,
        "can_deploy_control_chart": None,
        "r_chart_status": None,
        "mean_chart_status": None,
        "subgroup_rationality_ok": True,
    }
    return patterns, state


def run_rules(ctx: RuleContext) -> dict:
    """규칙 레지스트리 실행."""
    patterns, state = evaluate_control_chart(ctx)

    qq = ctx.qq_assessment or assess_qq_plot(ctx.raw_data)
    ctx.qq_assessment = qq
    norm_state = classify_normality_state(ctx.analysis.normality, qq, ctx.policy)
    state["normality_state"] = norm_state

    sorted_rules = sorted(RULES, key=lambda r: r.priority)
    for rule in sorted_rules:
        if rule.condition(ctx, state):
            rule.action(ctx, state)

    state["decision_log"].sort(key=lambda e: e.priority)
    return state


def build_capability_decision(
    cap: CapabilityResult | None,
    state: dict,
    metadata: AnalysisMetadata,
) -> CapabilityDecision | None:
    if cap is None:
        return None

    std_o = cap.std_overall
    ppu = (cap.usl - cap.mean) / (3 * std_o) if std_o > 0 and cap.usl is not None else 0.0
    ppl = (cap.mean - cap.lsl) / (3 * std_o) if std_o > 0 and cap.lsl is not None else 0.0

    status: CapabilityStatus = state.get("capability_status", "undetermined")
    focus = state.get("improvement_focus")
    primary_kpi = state.get("primary_kpi", "Cpk")
    primary_val = state.get("primary_kpi_value")
    cp_cpk_valid = state.get("cp_cpk_valid", False)
    validity_note = state.get("cp_cpk_validity_note", "Invalid")

    if cp_cpk_valid:
        cp_cpk_label = f"{primary_kpi} (Valid)" if primary_kpi == "Cpk" else f"Cpk (Valid)"
    else:
        cp_cpk_label = f"Cpk (Invalid — {validity_note.replace('Invalid — ', '')})"

    if primary_kpi == "Ppk":
        primary_label = f"Ppk = {primary_val:.3f}" if primary_val is not None else "Ppk"
    else:
        primary_label = f"Cpk = {primary_val:.3f}" if primary_val is not None else "Cpk"

    if focus == "maintain_monitor":
        rec = "현재 상태 유지 + 추이 모니터링"
    elif focus == "centering":
        rec = "산포보다 중심 치우침(centering) 개선 우선"
    elif focus == "variation":
        rec = "공정 산포 개선 우선"
    else:
        rec = "공정능력 재평가 필요"

    if not state.get("is_stable", True):
        rec = "공정 안정화 우선 → 안정화 후 Cp/Cpk 재평가; 현재는 Ppk 기준 성능 판단"

    nn = state.get("non_normal_capability") or {}
    cp_cpk_computable = cp_cpk_valid and state.get("is_stable", False)
    t_cap = state.get("transformed_capability")
    on_transformed = state.get("capability_on_transformed", False) and t_cap is not None
    out_pp = _nan_none(t_cap.pp if on_transformed else cap.pp)
    out_ppk = _nan_none(t_cap.ppk if on_transformed else cap.ppk)
    raw_cp = t_cap.cp if on_transformed else cap.cp
    raw_cpk = t_cap.cpk if on_transformed else cap.cpk
    out_cp = _nan_none(raw_cp) if cp_cpk_computable else None
    out_cpk = _nan_none(raw_cpk) if cp_cpk_computable else None
    if on_transformed and t_cap is not None:
        cp_reference = _nan_none(t_cap.cp)
        cpk_reference = _nan_none(t_cap.cpk)
    else:
        cp_reference = _nan_none(cap.cp)
        cpk_reference = _nan_none(cap.cpk)

    return CapabilityDecision(
        metric_basis=state.get("metric_basis", "CpCpk"),
        primary_kpi=primary_kpi,
        primary_kpi_value=primary_val,
        primary_kpi_label=primary_label,
        cp_cpk_valid=cp_cpk_valid,
        cp_cpk_validity_note=validity_note,
        cp=out_cp,
        cpk=out_cpk,
        pp=out_pp,
        ppk=out_ppk,
        cpu=cap.cpu,
        cpl=cap.cpl,
        ppu=ppu,
        ppl=ppl,
        cpk_ppk_gap=state.get("cpk_ppk_gap"),
        gap_interpretation=state.get("gap_interpretation", ""),
        process_level=state.get("process_level", ""),
        is_capable=state.get("is_capable", False),
        capability_status=status,
        improvement_focus=focus,
        recommendation=rec,
        cp_meaningful=state.get("cp_meaningful", metadata.spec_type == "two_sided"),
        capability_case=state.get("capability_case", ""),
        analysis_method=state.get("analysis_method", ""),
        analysis_method_rationale=state.get("analysis_method_rationale", ""),
        follow_up_priorities=state.get("follow_up_priorities", []),
        non_normal_applied=state.get("non_normal_applied", False),
        pp_non_normal=nn.get("Pp_nn"),
        ppk_non_normal=nn.get("Ppk_nn"),
        cp_non_normal=nn.get("Cp_nn") if cp_cpk_computable else None,
        cpk_non_normal=nn.get("Cpk_nn") if cp_cpk_computable else None,
        normality_transform_method=state.get("normality_transform_method"),
        capability_on_transformed=state.get("capability_on_transformed", False),
        cp_raw_reference=state.get("cp_raw_reference"),
        cpk_raw_reference=state.get("cpk_raw_reference"),
        pp_raw_reference=state.get("pp_raw_reference"),
        ppk_raw_reference=state.get("ppk_raw_reference"),
        cp_reference=cp_reference,
        cpk_reference=cpk_reference,
    )


def build_normality_decision(
    norm: NormalityResult,
    qq: QqPlotAssessment,
    state: dict,
    policy: SpcPolicyConfig,
) -> NormalityDecision:
    norm_state: NormalityState = state.get("normality_state", "undetermined")

    if norm_state == "normal":
        handling = "정규분포 가정 하에 공정능력 해석 가능"
    elif norm_state == "undetermined":
        handling = qq.message or "정규성 판정 불가 — 측정값 산포·표본수·열 매핑 확인"
    elif policy.strict_company_mode and norm_state in ("clearly_non_normal", "mixed_distribution_suspected"):
        handling = "원인 파악 → 조치 → 데이터 재수집 → 재분석"
    elif policy.advanced_spc_mode and not norm.is_normal:
        handling = (
            "원인 파악/조치/재수집 권고 + "
            "Box-Cox·Johnson 변환, 비정규 적합, 비모수 capability 옵션 검토"
        )
    elif norm_state == "borderline_non_normal":
        handling = "히스토그램·QQ plot 교차 확인 후 판정 보완"
    else:
        handling = "정규성 판정 불가 — 추가 데이터 확보"

    t_result = state.get("normality_transform_result")
    transform_attempts: list[dict] = []
    transform_summary: str | None = None
    if t_result is not None:
        transform_attempts = list(getattr(t_result, "attempts", None) or [])
        transform_summary = getattr(t_result, "notes", None) or None

    return NormalityDecision(
        test_name=norm.test_name,
        statistic=norm.statistic,
        p_value=norm.p_value,
        is_normal=norm.is_normal,
        normality_state=norm_state,
        qqplot_assessment=qq.to_dict(),
        handling_recommendation=handling,
        non_normal_detected=state.get("non_normal_detected", False)
        and norm_state not in ("normal", "undetermined", "borderline_non_normal"),
        applied_action=state.get("normality_action"),
        transform_method=state.get("normality_transform_method"),
        transform_success=state.get("normality_transform_applied", False),
        transform_p_value_after=(
            t_result.normality_after.p_value
            if t_result
            and getattr(t_result, "normality_after", None)
            else None
        ),
        transform_detail=state.get("normality_action"),
        transform_attempts=transform_attempts,
        transform_summary=transform_summary,
    )


def build_control_chart_decision(state: dict) -> ControlChartDecision:
    is_stable = state.get("is_stable", False)
    r_unstable = state.get("r_chart_status") == "unstable"
    mean_deferred = state.get("mean_chart_status") == "deferred"

    if is_stable and not r_unstable and not mean_deferred:
        status: StabilityStatus = "stable"
    else:
        status = "unstable"

    we_summaries = [
        WesternElectricViolationSummary(
            rule_id=v.rule_id,
            rule_name=v.rule_name,
            occurrence_count=v.occurrence_count,
            affected_subgroups=v.affected_subgroups,
        )
        for v in state.get("western_electric_violations", [])
    ]

    rec_parts: list[str] = []
    if r_unstable or mean_deferred:
        rec_parts.append(
            "R(산포) 관리도 불안정 — Unstable (Out of Control); 산포 원인 제거 우선, Cp/Cpk 사용 불가"
        )
    elif status == "unstable":
        rec_parts.append("Unstable (Out of Control) — 공정 안정화 후 재수집 및 관리한계 재설정")
    else:
        rec_parts.append("Stable (In Control) — 현 상태 유지, 정기 모니터링")

    if we_summaries:
        rec_parts.append(state.get("western_electric_summary", ""))

    company_interp: CompanyChartInterpretation | None = state.get("company_interpretation")
    company_decision = None
    if company_interp:
        company_decision = CompanyChartDecision(
            status=company_interp.status,
            detected_rules=[r.to_dict() for r in company_interp.detected_rules],
            summary_message=company_interp.summary_message,
            actions=company_interp.actions,
            mean_chart_deferred=company_interp.mean_chart_deferred,
            dispersion_abnormal=company_interp.dispersion_abnormal,
        )
        if company_interp.mean_chart_deferred:
            rec_parts.insert(
                0,
                "산포관리도 이상 → 평균관리도 신뢰 불가 (참고용)",
            )

    return ControlChartDecision(
        is_stable=is_stable and status == "stable",
        status=status,
        r_chart_status=state.get("r_chart_status"),
        mean_chart_status=state.get("mean_chart_status"),
        detected_patterns=state.get("detected_patterns", []),
        western_electric_violations=we_summaries,
        western_electric_summary=state.get("western_electric_summary", ""),
        decision_log=state.get("decision_log", []),
        recommendation="; ".join(rec_parts),
        company_interpretation=company_decision,
    )


def build_compliance_decision(state: dict) -> ComplianceDecision:
    deploy: DeployStatus = state.get("can_deploy_control_chart") or "undetermined"

    priority: list[str] = []
    if state.get("requires_recollection"):
        priority.append("데이터 재수집")
    if state.get("improvement_focus") == "variation":
        priority.append("산포 개선")
    elif state.get("improvement_focus") == "centering":
        priority.append("중심 이동")
    if state.get("requires_control_plan_review"):
        priority.append("관리계획서 검토")
    if state.get("requires_containment"):
        priority.append("봉쇄 검토")
    if state.get("requires_100pct_inspection"):
        priority.append("전수검사 검토")
    if not priority and deploy == "possible":
        priority.append("현상 유지 + 추이 모니터링")

    return ComplianceDecision(
        can_deploy_control_chart=deploy,
        requires_recollection=state.get("requires_recollection", False),
        requires_process_improvement=state.get("requires_process_improvement", False),
        requires_control_limit_reset=state.get("requires_control_limit_reset", False),
        requires_control_plan_review=state.get("requires_control_plan_review", False),
        requires_work_instruction_review=state.get("requires_work_instruction_review", False),
        requires_containment=state.get("requires_containment", False),
        requires_100pct_inspection=state.get("requires_100pct_inspection", False),
        requires_customer_exception_review=state.get("requires_customer_exception_review", False),
        priority_actions=priority,
    )


def infer_stability_label(status: StabilityStatus) -> str:
    return {
        "stable": "Stable (In Control)",
        "unstable": "Unstable (Out of Control)",
        "deferred": "Unstable (Out of Control)",
        "undetermined": "Unstable (Out of Control)",
    }.get(status, "Unstable (Out of Control)")


def infer_normality_label(state: NormalityState) -> str:
    return {
        "normal": "정규 (Normal)",
        "borderline_non_normal": "경계 (Borderline)",
        "clearly_non_normal": "비정규 (Non-normal)",
        "mixed_distribution_suspected": "비정규 (Mixed)",
        "undetermined": "미확정 (Undetermined)",
    }.get(state, "미확정 (Undetermined)")


def infer_capability_label(status: CapabilityStatus) -> str:
    return {
        "sufficient": "충분 (Sufficient)",
        "insufficient": "부족 (Insufficient)",
        "conditional": "조건부 (Conditional)",
        "undetermined": "미평가 (Undetermined)",
    }.get(status, "미평가 (Undetermined)")


def infer_deploy_label(deploy: DeployStatus) -> str:
    return {
        "possible": "가능 (Possible)",
        "not_possible": "불가 (Not Possible)",
        "exceptional": "예외적 가능 (Exceptional)",
        "undetermined": "불가 (Not Possible)",
    }.get(deploy, "불가 (Not Possible)")


def infer_cp_cpk_validity_label(valid: bool, note: str = "") -> str:
    if valid:
        return "Valid"
    if note.startswith("Invalid"):
        return note
    return "Invalid — Process Not Stable"
