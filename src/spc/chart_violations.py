"""관리도 해석 이상점 — 차트 마커용 포인트 수집."""
from __future__ import annotations

import pandas as pd

from src.spc.decision_models import SpcDecisionResult
from src.spc.statistics import SpcAnalysisResult


def collect_dispersion_violation_points(analysis: SpcAnalysisResult | None) -> set[int]:
    """R/S/MR 차트 UCL 초과 포인트 (1-based subgroup/point)."""
    if analysis is None:
        return set()
    cl = analysis.control_limits
    ooc: set[int] = set()

    if analysis.chart_type == "imr" and analysis.individual_stats is not None and cl.mr_limits:
        df = analysis.individual_stats
        ucl = cl.mr_limits["UCL"]
        for i, v in enumerate(df["MR"].to_numpy()):
            if not pd.isna(v) and float(v) > ucl:
                ooc.add(int(df["point"].iloc[i]))
        return ooc

    df = analysis.subgroup_stats
    if df is None:
        return ooc

    if analysis.chart_type == "xbar_r" and cl.r_limits and "R" in df.columns:
        ucl = cl.r_limits["UCL"]
        for i, v in enumerate(df["R"].to_numpy()):
            if float(v) > ucl:
                ooc.add(int(df["subgroup"].iloc[i]))
    elif analysis.chart_type == "xbar_s" and cl.s_limits and "S" in df.columns:
        ucl = cl.s_limits["UCL"]
        for i, v in enumerate(df["S"].to_numpy()):
            if float(v) > ucl:
                ooc.add(int(df["subgroup"].iloc[i]))
    return ooc


def collect_point_violation_labels(
    decision: SpcDecisionResult | None,
    analysis: SpcAnalysisResult | None,
) -> dict[int, list[str]]:
    """포인트별 이상 유형(규칙명) — hover·표시용."""
    if decision is None:
        return {}
    from src.spc.anomaly_point_table import build_anomaly_point_table

    table = build_anomaly_point_table(decision, analysis)
    if table.empty:
        return {}
    point_col = table.columns[0]
    grouped: dict[int, list[str]] = {}
    for _, row in table.iterrows():
        pid = int(row[point_col])
        name = str(row.get("규칙명", "")).strip()
        if not name:
            continue
        if name not in grouped.setdefault(pid, []):
            grouped[pid].append(name)
    return grouped


def collect_chart_violation_points(
    decision: SpcDecisionResult | None,
    analysis: SpcAnalysisResult | None,
) -> set[int]:
    """1-based subgroup/point 번호 집합 (회사 표준 규칙 + 관리한계 이탈)."""
    points: set[int] = set()
    if analysis and getattr(analysis, "out_of_control_points", None):
        points.update(int(p) for p in analysis.out_of_control_points)
    if decision is None:
        return points

    cc = decision.control_chart
    for pat in cc.detected_patterns:
        points.update(int(p) for p in pat.affected_points)
    for v in cc.western_electric_violations:
        points.update(int(p) for p in v.affected_subgroups)

    company = cc.company_interpretation
    if company:
        for rule in company.detected_rules:
            for key in ("matchedPoints", "matched_points"):
                raw = rule.get(key)
                if raw:
                    points.update(int(p) for p in raw)
    return points


def expand_violation_row_indices(
    sample_df: pd.DataFrame,
    violation_points: set[int],
    chart_type: str | None,
) -> set[int]:
    """개별값 시계열용 1-based 행 순번 (Xbar는 해당 subgroup 내 모든 측정값)."""
    if not violation_points or sample_df is None or sample_df.empty:
        return set()

    if chart_type in ("xbar_s", "xbar_r") and "subgroup_id" in sample_df.columns:
        rows: set[int] = set()
        sg_list = sample_df["subgroup_id"].astype(int).tolist()
        for pid in violation_points:
            for pos, sg in enumerate(sg_list, start=1):
                if sg == int(pid):
                    rows.add(pos)
        return rows

    return {int(p) for p in violation_points}


def violation_measurement_values(
    sample_df: pd.DataFrame,
    violation_points: set[int],
    chart_type: str | None,
) -> list[float]:
    """히스토그램·분포 차트용 이상 측정값."""
    if sample_df is None or sample_df.empty or "value" not in sample_df.columns:
        return []
    row_ids = expand_violation_row_indices(sample_df, violation_points, chart_type)
    vals: list[float] = []
    for rid in sorted(row_ids):
        idx = rid - 1
        if 0 <= idx < len(sample_df):
            vals.append(float(sample_df.iloc[idx]["value"]))
    return vals
