"""변동성 기반 Worst 이상점 검토 — 선정·우선순위·상세 해석."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src.spc.anomaly_point_table import build_anomaly_point_table
from src.spc.data_quality_diagnostics import DataQualityReport, analyze_data_quality
from src.spc.decision_models import SpcDecisionResult
from src.spc.pattern_catalog import PATTERN_CATALOG
from src.spc.spc_rules import RULE_DEFINITIONS
from src.spc.statistics import SpcAnalysisResult

RULE_NAME_TO_ID: dict[str, str] = {
    "규격상한/하한 이탈": "SPEC_LIMIT_OUT",
    "관리상한/하한 이탈": "CONTROL_LIMIT_OUT",
    "관리한계 이탈": "CONTROL_LIMIT_OUT",
    "주기성 (Oscillation)": "OSCILLATION",
    "2σ/3σ 편중": "ZONE_RULE_1",
    "중심 집중": "HUGGING",
    "한쪽 집중 (Shift)": "SHIFT",
    "경향성 (Trend)": "TREND",
    "1σ 외 편중": "ZONE_RULE_2",
    "과도 분산": "EXCESS_DISPERSION",
}

PATTERN_TO_RULE: dict[str, str] = {
    "control_limit_violation": "CONTROL_LIMIT_OUT",
    "company_spec_limit_out": "SPEC_LIMIT_OUT",
    "company_control_limit_out": "CONTROL_LIMIT_OUT",
    "company_oscillation": "OSCILLATION",
    "company_zone_rule_1": "ZONE_RULE_1",
    "company_hugging": "HUGGING",
    "company_shift": "SHIFT",
    "company_trend": "TREND",
    "company_zone_rule_2": "ZONE_RULE_2",
    "company_excess_dispersion": "EXCESS_DISPERSION",
}

IMPROVEMENT_BY_RULE: dict[str, list[str]] = {
    "SPEC_LIMIT_OUT": [
        "USL/LSL 이탈 LOT·공정·측정 이력을 즉시 확인하고 견리·재작업 여부를 판단합니다.",
        "부적합 원인 제거 후 해당 구간 데이터를 재채취합니다.",
    ],
    "CONTROL_LIMIT_OUT": [
        "UCL/LCL 이탈 시점 전후 4M1E·설비·원재료 변경 이력을 확인합니다.",
        "특별원인 제거 후 관리도를 재평가합니다.",
    ],
    "OSCILLATION": [
        "교대·Cycle·환경 주기와 측정값 진동의 상관을 분석합니다.",
        "주기 원인 제거 전까지 해당 구간은 참고용으로만 사용합니다.",
    ],
    "ZONE_RULE_1": [
        "공정 중심 이동 초기 신호 — 셋업·영점·공구 상태를 점검합니다.",
        "2σ 편중 방향에 맞춰 평균 보정을 검토합니다.",
    ],
    "HUGGING": [
        "측정계 분해능·R&R 및 데이터 스택킹 여부를 점검합니다.",
        "±1σ 내부 과도 집중 시 게이지·반올림 설정을 확인합니다.",
    ],
    "SHIFT": [
        "중심선 한쪽 치우침 방향에 맞춰 셋업·영점·공구 상태를 점검합니다.",
        "평균 위치 보정 후 연속 모니터링으로 재발 여부를 확인합니다.",
    ],
    "TREND": [
        "공구 마모·열화·작업 피로 등 시간에 따른 드리프트 원인을 조사합니다.",
        "예방보전·공정 파라미터 재튜닝 후 추세 소멸 여부를 확인합니다.",
    ],
    "ZONE_RULE_2": [
        "1σ 외 편중 — 분포 비대칭 원인(원료·혼합·측정 조건)을 확인합니다.",
        "한쪽 꼬리 증가 시 공정 조건 재최적화를 검토합니다.",
    ],
    "EXCESS_DISPERSION": [
        "연속 ±1σ 외부 — 공정 변동 증가 원인을 산포 관리도와 연계 분석합니다.",
        "측정 시스템 및 원료·LOT 간 산포 차이를 확인합니다.",
    ],
}


@dataclass
class VariabilityPointReview:
    point_id: int
    point_label: str
    variability_score: float
    priority: str  # High | Mid | Low
    rule_ids: list[str]
    rule_names: list[str]
    criteria: list[str]
    reasons: list[str] = field(default_factory=list)
    cause_codes: str = ""
    is_worst: bool = False
    measurement_value: float | None = None
    deviation_sigma: float | None = None
    chart_distance_score: float = 0.0
    dispersion_score: float = 0.0
    score_breakdown: str = ""
    variability_summary: str = ""
    likely_causes: list[str] = field(default_factory=list)
    improvement_actions: list[str] = field(default_factory=list)


@dataclass
class VariabilityReviewResult:
    point_label: str
    process_variability_index: float
    spec_relative_sigma: float | None
    reviews: list[VariabilityPointReview]
    worst: list[VariabilityPointReview]
    data_quality_notes: list[str]


def _rule_id_from_name(name: str, pattern_id: str | None = None) -> str:
    if pattern_id and pattern_id in PATTERN_TO_RULE:
        return PATTERN_TO_RULE[pattern_id]
    if name in RULE_NAME_TO_ID:
        return RULE_NAME_TO_ID[name]
    for rid, defn in RULE_DEFINITIONS.items():
        if defn.get("rule_name") == name:
            return rid
    return "CONTROL_LIMIT_OUT" if "이탈" in name else "SHIFT"


def _data_quality_flags(report: DataQualityReport) -> dict[str, bool]:
    codes = {f.code for f in report.findings if f.severity in ("warning", "critical")}
    return {
        "isMixedPopulation": "MIXED_MEASUREMENT_POINTS" in codes or "MULTIMODAL_CLUSTERS" in codes,
        "isTimeSeriesOrdered": "TIME_ORDER_MISMATCH" not in codes,
        "hasResolutionIssue": "DISCRETE_VALUES" in codes,
    }


def _process_variability_index(
    analysis: SpcAnalysisResult,
    decision: SpcDecisionResult,
    dq_flags: dict[str, bool],
) -> tuple[float, float | None]:
    cap = analysis.capability
    cl = analysis.control_limits
    sigma = cl.sigma_estimate if cl and cl.sigma_estimate else None
    if sigma is None and cap:
        sigma = cap.std_within or cap.std_overall
    spec_rel = None
    score = 0.0
    if cap and cap.usl is not None and cap.lsl is not None and sigma:
        span = cap.usl - cap.lsl
        if span > 0:
            spec_rel = float(sigma / span)
            score += spec_rel * 100.0
    if cap and decision.capability:
        cpk = decision.capability.cpk
        if not decision.capability.cp_cpk_valid:
            score += 25.0
        elif cpk is not None:
            score += max(0.0, (1.67 - cpk) * 15.0)
    if not decision.normality.is_normal:
        score += 10.0
    if dq_flags.get("isMixedPopulation"):
        score += 20.0
    if not dq_flags.get("isTimeSeriesOrdered", True):
        score += 12.0
    if dq_flags.get("hasResolutionIssue"):
        score += 8.0
    if not decision.control_chart.is_stable:
        score += 15.0
    return score, spec_rel


def _sigma_zone_width(cl: float, ucl: float, lcl: float) -> float:
    up = abs(ucl - cl) / 3.0 if ucl != cl else 0.0
    lo = abs(cl - lcl) / 3.0 if lcl != cl else 0.0
    return max(up, lo, 1e-12)


def _chart_distance_score(point_id: int, analysis: SpcAnalysisResult) -> tuple[float, float | None, float | None]:
    """관리도 상 실제 편차 — Xbar/I가 CL에서 얼마나 떨어졌는지(σ 환산)."""
    climits = analysis.control_limits
    if analysis.chart_type in ("xbar_s", "xbar_r") and analysis.subgroup_stats is not None:
        sg = analysis.subgroup_stats
        row = sg.loc[sg["subgroup"] == point_id]
        if row.empty:
            return 0.0, None, None
        xbar = float(row["Xbar"].iloc[0])
        limits = climits.xbar_limits or {}
        cl, ucl, lcl = limits.get("CL"), limits.get("UCL"), limits.get("LCL")
        if cl is None or ucl is None or lcl is None:
            return 0.0, xbar, None
        zone = _sigma_zone_width(cl, ucl, lcl)
        if xbar > ucl:
            dev = (xbar - ucl) / zone + 3.0
        elif xbar < lcl:
            dev = (lcl - xbar) / zone + 3.0
        else:
            dev = abs(xbar - cl) / zone
        return min(100.0, dev * 12.0), xbar, dev

    if analysis.chart_type == "imr" and analysis.individual_stats is not None:
        row = analysis.individual_stats.loc[analysis.individual_stats["point"] == point_id]
        if row.empty:
            return 0.0, None, None
        val = float(row["I"].iloc[0])
        limits = climits.i_limits or {}
        cl, ucl, lcl = limits.get("CL"), limits.get("UCL"), limits.get("LCL")
        if cl is None or ucl is None or lcl is None:
            return 0.0, val, None
        zone = _sigma_zone_width(cl, ucl, lcl)
        if val > ucl:
            dev = (val - ucl) / zone + 3.0
        elif val < lcl:
            dev = (lcl - val) / zone + 3.0
        else:
            dev = abs(val - cl) / zone
        return min(100.0, dev * 12.0), val, dev

    return 0.0, None, None


def _dispersion_subgroup_score(point_id: int, analysis: SpcAnalysisResult) -> float:
    """산포 관리도(R/S) 기여 — 해당 subgroup 산포가 UCL에 가까울수록 가산."""
    if analysis.subgroup_stats is None:
        return 0.0
    sg = analysis.subgroup_stats
    row = sg.loc[sg["subgroup"] == point_id]
    if row.empty:
        return 0.0
    climits = analysis.control_limits
    if analysis.chart_type == "xbar_r" and "R" in row.columns and climits.r_limits:
        val = float(row["R"].iloc[0])
        ucl = climits.r_limits.get("UCL")
        if ucl and ucl > 0:
            return min(40.0, max(0.0, val / ucl) * 40.0)
    if analysis.chart_type == "xbar_s" and "S" in row.columns and climits.s_limits:
        val = float(row["S"].iloc[0])
        ucl = climits.s_limits.get("UCL")
        if ucl and ucl > 0:
            return min(40.0, max(0.0, val / ucl) * 40.0)
    return 0.0


def _point_variability_score(chart_dist: float, disp_score: float) -> float:
    """규칙 가중치 없이 차트·산포 중 최대 변동성으로 순위."""
    return max(chart_dist, disp_score)


def _collect_point_rules(
    decision: SpcDecisionResult,
    analysis: SpcAnalysisResult | None,
) -> dict[int, list[dict]]:
    """포인트별 규칙 정보."""
    table = build_anomaly_point_table(decision, analysis)
    if table.empty:
        return {}
    point_col = table.columns[0]
    grouped: dict[int, list[dict]] = {}
    for _, row in table.iterrows():
        pid = int(row[point_col])
        name = str(row.get("규칙명", row.get("이상 유형", "")))
        rid = _rule_id_from_name(name)
        grouped.setdefault(pid, []).append({
            "rule_id": rid,
            "rule_name": name,
            "criterion": str(row.get("조건", row.get("판정 기준", ""))),
            "reason": str(row.get("해석 의미", row.get("이상 사유", ""))),
            "cause_codes": "",
        })
    return grouped


def _build_causes(rule_ids: list[str]) -> list[str]:
    causes: list[str] = []
    for rid in rule_ids:
        defn = RULE_DEFINITIONS.get(rid, {})
        interp = defn.get("interpretation")
        if interp and interp not in causes:
            causes.append(interp)
        pat_key = next((k for k, v in PATTERN_TO_RULE.items() if v == rid), None)
        if pat_key and pat_key in PATTERN_CATALOG:
            for c in PATTERN_CATALOG[pat_key].likely_causes:
                if c not in causes:
                    causes.append(c)
    return causes[:8]


def _build_improvements(rule_ids: list[str]) -> list[str]:
    actions: list[str] = []
    for rid in rule_ids:
        for a in IMPROVEMENT_BY_RULE.get(rid, []):
            if a not in actions:
                actions.append(a)
        pat_key = next((k for k, v in PATTERN_TO_RULE.items() if v == rid), None)
        if pat_key and pat_key in PATTERN_CATALOG:
            for a in PATTERN_CATALOG[pat_key].recommended_actions:
                if a not in actions:
                    actions.append(a)
    return actions[:6]


def _variability_summary(
    point_id: int,
    rule_ids: list[str],
    rule_names: list[str],
    deviation_sigma: float | None,
    measurement_value: float | None,
    spec_rel: float | None,
    chart_distance_score: float,
    score_breakdown: str,
) -> str:
    parts: list[str] = []
    parts.append(
        f"변동성 점수 {chart_distance_score:.1f} — 관리도·산포 중 최대 편차 기준 "
        f"({score_breakdown})."
    )
    if rule_names:
        parts.append(f"감지 규칙: {', '.join(rule_names)}.")
    if deviation_sigma is not None:
        parts.append(f"중심선 대비 약 {deviation_sigma:.2f}σ 위치입니다.")
    if measurement_value is not None:
        parts.append(f"차트 표시값: {measurement_value:.4f}.")
    if spec_rel is not None and spec_rel > 0.15:
        parts.append(f"공정 전체 σ/공차({spec_rel:.1%})도 높습니다.")
    return " ".join(parts)


def _assign_priority(rank: int, is_worst: bool, score: float, scores: list[float]) -> str:
    if is_worst:
        return "High"
    if not scores:
        return "Low"
    median = float(np.median(scores))
    if score >= median:
        return "Mid"
    return "Low"


def build_variability_review(
    decision: SpcDecisionResult,
    analysis: SpcAnalysisResult,
    sample_df: pd.DataFrame | None = None,
    filtered_df: pd.DataFrame | None = None,
    worst_count: int = 5,
    min_worst: int = 3,
) -> VariabilityReviewResult:
    """변동성 기반 이상점 검토표 + Worst 3~5 상세."""
    point_label = "Subgroup" if analysis.chart_type in ("xbar_s", "xbar_r") else "Point"
    dq = analyze_data_quality(sample_df, filtered_df)
    dq_flags = _data_quality_flags(dq)
    proc_idx, spec_rel = _process_variability_index(analysis, decision, dq_flags)

    point_rules = _collect_point_rules(decision, analysis)
    if not point_rules:
        return VariabilityReviewResult(
            point_label=point_label,
            process_variability_index=proc_idx,
            spec_relative_sigma=spec_rel,
            reviews=[],
            worst=[],
            data_quality_notes=[f.detail for f in dq.findings if f.severity != "info"],
        )

    reviews: list[VariabilityPointReview] = []
    for pid, rules in point_rules.items():
        rule_ids = list(dict.fromkeys(r["rule_id"] for r in rules))
        rule_names = list(dict.fromkeys(r["rule_name"] for r in rules))
        criteria = list(dict.fromkeys(r["criterion"] for r in rules if r["criterion"]))
        reasons = list(dict.fromkeys(r["reason"] for r in rules if r["reason"]))
        code_parts = list(dict.fromkeys(r["cause_codes"] for r in rules if r["cause_codes"]))
        cause_codes = " | ".join(code_parts)

        chart_dist, val, dev_sigma = _chart_distance_score(pid, analysis)
        disp_score = _dispersion_subgroup_score(pid, analysis)
        score = _point_variability_score(chart_dist, disp_score)
        dominant = "차트 편차" if chart_dist >= disp_score else "산포"
        dominant_val = chart_dist if chart_dist >= disp_score else disp_score
        breakdown = (
            f"max(차트 {chart_dist:.1f}, 산포 {disp_score:.1f}) = {score:.1f} "
            f"— {dominant} {dominant_val:.1f}"
        )

        reviews.append(
            VariabilityPointReview(
                point_id=pid,
                point_label=point_label,
                variability_score=round(score, 2),
                priority="Low",
                rule_ids=rule_ids,
                rule_names=rule_names,
                criteria=criteria,
                reasons=reasons,
                cause_codes=cause_codes,
                measurement_value=val,
                deviation_sigma=round(dev_sigma, 3) if dev_sigma is not None else None,
                chart_distance_score=round(chart_dist, 2),
                dispersion_score=round(disp_score, 2),
                score_breakdown=breakdown,
            )
        )

    reviews.sort(key=lambda x: x.variability_score, reverse=True)
    all_scores = [r.variability_score for r in reviews]
    n_worst = min(worst_count, max(min_worst, len(reviews))) if len(reviews) >= min_worst else len(reviews)

    for i, rev in enumerate(reviews):
        is_worst = i < n_worst
        rev.is_worst = is_worst
        rev.priority = _assign_priority(i, is_worst, rev.variability_score, all_scores)
        if is_worst:
            rev.likely_causes = _build_causes(rev.rule_ids)
            rev.improvement_actions = _build_improvements(rev.rule_ids)
            rev.variability_summary = _variability_summary(
                rev.point_id,
                rev.rule_ids,
                rev.rule_names,
                rev.deviation_sigma,
                rev.measurement_value,
                spec_rel,
                rev.variability_score,
                rev.score_breakdown,
            )

    worst = [r for r in reviews if r.is_worst]
    notes = [f"{f.title}: {f.detail}" for f in dq.findings if f.severity in ("warning", "critical")]

    return VariabilityReviewResult(
        point_label=point_label,
        process_variability_index=round(proc_idx, 2),
        spec_relative_sigma=spec_rel,
        reviews=reviews,
        worst=worst,
        data_quality_notes=notes,
    )


def review_to_dataframe(result: VariabilityReviewResult) -> pd.DataFrame:
    if not result.reviews:
        return pd.DataFrame(columns=[
            "Worst",
            result.point_label,
            "변동성 점수",
            "차트 편차",
            "산포",
            "우선순위",
            "이상 유형",
            "판정 기준",
            "이상 사유",
            "원인 코드",
        ])
    rows = []
    for r in result.reviews:
        rows.append({
            "Worst": "★" if r.is_worst else "",
            result.point_label: r.point_id,
            "변동성 점수": r.variability_score,
            "차트 편차": r.chart_distance_score,
            "산포": r.dispersion_score,
            "우선순위": r.priority,
            "이상 유형": ", ".join(r.rule_names),
            "판정 기준": " | ".join(r.criteria),
            "이상 사유": " | ".join(r.reasons),
            "원인 코드": r.cause_codes,
        })
    return pd.DataFrame(rows)
