"""SPC 회사 기준 판정 규칙 엔진."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from src.spc.decision_models import (
    AnalysisMetadata,
    CapabilityDecision,
    CapabilityStatus,
    ComplianceDecision,
    ControlChartDecision,
    DecisionLogEntry,
    DeployStatus,
    DetectedPattern,
    NormalityDecision,
    NormalityState,
    StabilityStatus,
)
from src.spc.pattern_catalog import PATTERN_CATALOG, get_pattern_meta
from src.spc.policy_config import SpcPolicyConfig, StageType
from src.spc.qqplot_assessment import QqPlotAssessment, assess_qq_plot
from src.spc.statistics import CapabilityResult, NormalityResult, SpcAnalysisResult


@dataclass
class RuleContext:
    """규칙 평가 컨텍스트."""

    analysis: SpcAnalysisResult
    policy: SpcPolicyConfig
    metadata: AnalysisMetadata
    raw_data: np.ndarray
    qq_assessment: QqPlotAssessment | None = None


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


def detect_control_patterns(ctx: RuleContext) -> list[DetectedPattern]:
    """관리도 이상 패턴 감지."""
    patterns: list[DetectedPattern] = []
    policy = ctx.policy
    values, cl, ucl, lcl, point_ids = _get_mean_chart_values(ctx)
    n = len(values)

    if n == 0:
        return patterns

    # control_limit_violation
    ooc_idx = [i for i, v in enumerate(values) if v > ucl or v < lcl]
    if ooc_idx:
        pts = [point_ids[i] for i in ooc_idx]
        patterns.append(_meta_to_pattern("control_limit_violation", pts))

    # run_7_same_side
    run_n = policy.run_rule_points
    if n >= run_n:
        for start in range(n - run_n + 1):
            segment = values[start : start + run_n]
            if np.all(segment > cl) or np.all(segment < cl):
                pts = point_ids[start : start + run_n]
                patterns.append(_meta_to_pattern("run_7_same_side", pts))
                break

    # trend_7_increasing_or_decreasing
    trend_n = policy.trend_rule_points
    if n >= trend_n:
        for start in range(n - trend_n + 1):
            segment = values[start : start + trend_n]
            diffs = np.diff(segment)
            if np.all(diffs > 0) or np.all(diffs < 0):
                pts = point_ids[start : start + trend_n]
                patterns.append(_meta_to_pattern("trend_7_increasing_or_decreasing", pts))
                break

    # centerline_bias — 8/10 이상 동일측
    above = int(np.sum(values > cl))
    below = int(np.sum(values < cl))
    if n >= 10 and (above >= 8 or below >= 8):
        patterns.append(_meta_to_pattern("centerline_bias"))

    # excessive_scatter — R/S/MR UCL 초과
    disp_ooc = _get_dispersion_ooc_points(ctx)
    if disp_ooc:
        patterns.append(_meta_to_pattern("excessive_scatter", disp_ooc))

    # near_control_limit — UCL/LCL 1σ 이내 4점 이상
    if ucl != lcl:
        half = (ucl - lcl) / 2
        near_ucl = ucl - half / 3
        near_lcl = lcl + half / 3
        near_count = int(np.sum((values >= near_ucl) | (values <= near_lcl)))
        if near_count >= 4:
            patterns.append(_meta_to_pattern("near_control_limit"))

    # periodicity — 자기상관 휴리스틱 (lag-2~5 상관, 오탐 방지 강화)
    if n >= 20:
        hits = 0
        for lag in range(2, min(6, n // 2)):
            corr = np.corrcoef(values[:-lag], values[lag:])[0, 1]
            if not np.isnan(corr) and abs(corr) > 0.75:
                hits += 1
        if hits >= 2:
            patterns.append(_meta_to_pattern("periodicity"))

    # 중복 pattern_id 제거 (첫 번째만)
    seen: set[str] = set()
    unique: list[DetectedPattern] = []
    for p in patterns:
        if p.pattern_id not in seen:
            seen.add(p.pattern_id)
            unique.append(p)
    return unique


def infer_spec_type(usl: float | None, lsl: float | None) -> str:
    if usl is not None and lsl is not None:
        return "two_sided"
    if usl is not None:
        return "upper_only"
    if lsl is not None:
        return "lower_only"
    return "two_sided"


def classify_normality_state(
    norm: NormalityResult,
    qq: QqPlotAssessment,
    policy: SpcPolicyConfig,
) -> NormalityState:
    if norm.n < 3:
        return "undetermined"
    if norm.is_normal and qq.state_hint == "normal":
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


def _rule_stage_capability(ctx: RuleContext, state: dict) -> None:
    cap = ctx.analysis.capability
    if cap is None:
        state["capability_status"] = "undetermined"
        _log(state, "CAPABILITY_MISSING", "capability not calculated -> undetermined", 20)
        return

    stage = ctx.metadata.stage
    width_th, center_th = ctx.policy.capability_thresholds(stage)  # type: ignore[arg-type]
    basis = "CpCpk" if stage == "mass_production" else "PpPpk"
    state["metric_basis"] = basis

    _log(
        state,
        "STAGE_CAPABILITY",
        f"stage={stage} -> {basis} rule applied (threshold width={width_th}, center={center_th})",
        30,
    )

    if basis == "CpCpk":
        width_val, center_val = cap.cp, cap.cpk
        width_name, center_name = "Cp", "Cpk"
    else:
        width_val, center_val = cap.pp, cap.ppk
        width_name, center_name = "Pp", "Ppk"

    cp_meaningful = ctx.metadata.spec_type == "two_sided"
    state["cp_meaningful"] = cp_meaningful

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
    Rule("R_CHART_FIRST", lambda c, s: c.analysis.chart_type == "xbar_r", _rule_r_chart_first, 5),
    Rule("DISPERSION_STABILITY", lambda c, s: c.analysis.chart_type in ("xbar_s", "imr"), _rule_dispersion_stability, 8),
    Rule("MEAN_CHART_STABILITY", lambda c, s: True, _rule_mean_chart_stability, 10),
    Rule("STAGE_CAPABILITY", lambda c, s: True, _rule_stage_capability, 15),
    Rule("SPECIAL_CHARACTERISTIC", lambda c, s: c.metadata.special_characteristic, _rule_special_characteristic, 18),
    Rule("CUSTOMER_EXCEPTION", lambda c, s: c.metadata.customer_exception_mode, _rule_customer_exception, 20),
    Rule("NORMALITY_STRICT", lambda c, s: True, _rule_normality_strict, 14),
    Rule("DEPLOY_CONTROL_CHART", lambda c, s: True, _rule_deploy_control_chart, 6),
]


def _has_stability_breaking_signal(patterns: list[DetectedPattern], ooc: list[int]) -> bool:
    """안정성 판정에 영향을 주는 critical/high 패턴 또는 OOC."""
    if ooc:
        return True
    return any(p.severity in ("critical", "high") for p in patterns)


def evaluate_control_chart(ctx: RuleContext) -> tuple[list[DetectedPattern], dict]:
    """관리도 패턴 감지 및 안정성 초기 상태."""
    patterns = detect_control_patterns(ctx)
    ooc = ctx.analysis.out_of_control_points
    state: dict = {
        "detected_patterns": patterns,
        "is_stable": not _has_stability_breaking_signal(patterns, ooc),
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
    ppu = (cap.usl - cap.mean) / (3 * std_o) if std_o > 0 else 0.0
    ppl = (cap.mean - cap.lsl) / (3 * std_o) if std_o > 0 else 0.0

    status: CapabilityStatus = state.get("capability_status", "undetermined")
    focus = state.get("improvement_focus")

    if focus == "maintain_monitor":
        rec = "현재 상태 유지 + 추이 모니터링"
    elif focus == "centering":
        rec = "산포보다 중심 치우침(centering) 개선 우선"
    elif focus == "variation":
        rec = "공정 산포 개선 우선"
    else:
        rec = "공정능력 재평가 필요"

    return CapabilityDecision(
        metric_basis=state.get("metric_basis", "CpCpk"),
        cp=cap.cp,
        cpk=cap.cpk,
        pp=cap.pp,
        ppk=cap.ppk,
        cpu=cap.cpu,
        cpl=cap.cpl,
        ppu=ppu,
        ppl=ppl,
        is_capable=state.get("is_capable", False),
        capability_status=status,
        improvement_focus=focus,
        recommendation=rec,
        cp_meaningful=state.get("cp_meaningful", metadata.spec_type == "two_sided"),
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

    return NormalityDecision(
        test_name=norm.test_name,
        statistic=norm.statistic,
        p_value=norm.p_value,
        is_normal=norm.is_normal,
        normality_state=norm_state,
        qqplot_assessment=qq.to_dict(),
        handling_recommendation=handling,
    )


def build_control_chart_decision(state: dict) -> ControlChartDecision:
    is_stable = state.get("is_stable", False)
    if state.get("mean_chart_status") == "deferred":
        status: StabilityStatus = "deferred"
    elif is_stable:
        status = "stable"
    elif state.get("is_stable") is False:
        status = "unstable"
    else:
        status = "undetermined"

    rec_parts: list[str] = []
    if status == "deferred":
        rec_parts.append("R(산포) 관리도 불안정 — 평균 관리도 해석 보류, 산포 원인 제거 우선")
    elif status == "unstable":
        rec_parts.append("공정 안정화 후 재수집 및 관리한계 재설정")
    else:
        rec_parts.append("현 상태 유지, 정기 모니터링")

    return ControlChartDecision(
        is_stable=is_stable,
        status=status,
        r_chart_status=state.get("r_chart_status"),
        mean_chart_status=state.get("mean_chart_status"),
        detected_patterns=state.get("detected_patterns", []),
        decision_log=state.get("decision_log", []),
        recommendation="; ".join(rec_parts),
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
        "stable": "안정",
        "unstable": "불안정",
        "deferred": "판정불가",
        "undetermined": "판정불가",
    }.get(status, "판정불가")


def infer_normality_label(state: NormalityState) -> str:
    return {
        "normal": "정규",
        "borderline_non_normal": "경계",
        "clearly_non_normal": "비정규",
        "mixed_distribution_suspected": "비정규",
        "undetermined": "판정불가",
    }.get(state, "판정불가")


def infer_capability_label(status: CapabilityStatus) -> str:
    return {
        "sufficient": "충분",
        "insufficient": "부족",
        "conditional": "조건부",
        "undetermined": "판정불가",
    }.get(status, "판정불가")


def infer_deploy_label(deploy: DeployStatus) -> str:
    return {
        "possible": "가능",
        "not_possible": "불가",
        "exceptional": "예외적 가능",
        "undetermined": "판정불가",
    }.get(deploy, "판정불가")
