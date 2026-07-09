"""Excel 역추적 — 이상점·관리한계·규격·공정능력 미달 표시."""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from src.spc.anomaly_point_table import build_anomaly_point_table
from src.spc.chart_violations import (
    collect_dispersion_violation_points,
    collect_point_violation_labels,
)
from src.spc.decision_models import SpcDecisionResult
from src.spc.statistics import SpcAnalysisResult


def _collect_mean_chart_ooc_subgroups(analysis: SpcAnalysisResult) -> set[int]:
    cl = analysis.control_limits
    ooc: set[int] = set()
    if analysis.chart_type == "imr" and analysis.individual_stats is not None and cl.i_limits:
        ucl, lcl = cl.i_limits["UCL"], cl.i_limits["LCL"]
        df = analysis.individual_stats
        for _, row in df.iterrows():
            v = row.get("I")
            if v is not None and not pd.isna(v):
                if float(v) > ucl or float(v) < lcl:
                    ooc.add(int(row["point"]))
        return ooc

    df = analysis.subgroup_stats
    if df is None or not cl.xbar_limits or "Xbar" not in df.columns:
        return ooc
    ucl, lcl = cl.xbar_limits["UCL"], cl.xbar_limits["LCL"]
    for _, row in df.iterrows():
        v = float(row["Xbar"])
        if v > ucl or v < lcl:
            ooc.add(int(row["subgroup"]))
    return ooc


def _spec_limits_from_analysis(analysis: SpcAnalysisResult) -> tuple[float | None, float | None]:
    cap = analysis.capability
    if cap is None:
        return None, None
    return cap.usl, cap.lsl


def _value_spec_violation(val: float, usl: float | None, lsl: float | None) -> bool:
    if usl is not None and val > usl:
        return True
    if lsl is not None and val < lsl:
        return True
    return False


def build_capability_trace_summary(
    decision: SpcDecisionResult | None,
    analysis: SpcAnalysisResult | None = None,
) -> pd.DataFrame:
    """공정능력 미달·개선 포인트 요약 (역추적 가이드)."""
    if decision is None or decision.capability is None:
        return pd.DataFrame([{
            "항목": "공정능력",
            "결과": "USL/LSL 미지정 또는 미산출",
            "미달/주의": "—",
            "역추적 안내": "규격을 지정한 뒤 재분석하세요.",
        }])

    cap = decision.capability
    v = decision.verdict_summary
    rows: list[dict[str, str]] = [
        {
            "항목": "공정능력 판정",
            "결과": v.capability_verdict,
            "미달/주의": "Y" if cap.capability_status == "insufficient" else (
                "△" if cap.capability_status == "conditional" else "N"
            ),
            "역추적 안내": cap.recommendation or "—",
        },
        {
            "항목": "Primary KPI",
            "결과": cap.primary_kpi_label,
            "미달/주의": "Y" if not cap.is_capable else "N",
            "역추적 안내": (
                f"개선 초점: {cap.improvement_focus}" if cap.improvement_focus else "현 수준 유지"
            ),
        },
        {
            "항목": "공정 상태",
            "결과": v.process_stability,
            "미달/주의": "Y" if not decision.control_chart.is_stable else "N",
            "역추적 안내": (
                "불안정 → 역추적_Subgroup·채취표본의 이상Rule·관리한계 열 우선 확인"
                if not decision.control_chart.is_stable
                else "안정 — 규격이탈 행·히스토그램 꼬리 확인"
            ),
        },
    ]
    if cap.improvement_focus:
        focus_guide = {
            "variation": "산포 과다 — 역추적_Subgroup 산포_관리이탈·R/S 큰 군 확인",
            "centering": "중심 치우침 — Xbar 관리이탈·규격 한쪽 편향 subgroup 확인",
            "maintain_monitor": "기준 충족 — 추이 모니터링",
        }
        rows.append({
            "항목": "개선 초점",
            "결과": cap.improvement_focus,
            "미달/주의": "Y" if cap.capability_status != "sufficient" else "N",
            "역추적 안내": focus_guide.get(cap.improvement_focus, "—"),
        })
    if cap.cpk_ppk_gap is not None:
        rows.append({
            "항목": "Cpk−Ppk Gap",
            "결과": f"{cap.cpk_ppk_gap:.3f}",
            "미달/주의": "△" if abs(cap.cpk_ppk_gap) > 0.1 else "N",
            "역추적 안내": cap.gap_interpretation or "—",
        })

    usl, lsl = _spec_limits_from_analysis(analysis) if analysis else (None, None)
    if usl is not None or lsl is not None:
        spec_txt = []
        if usl is not None:
            spec_txt.append(f"USL={usl:g}")
        if lsl is not None:
            spec_txt.append(f"LSL={lsl:g}")
        rows.append({
            "항목": "규격",
            "결과": ", ".join(spec_txt),
            "미달/주의": "—",
            "역추적 안내": "역추적_채취표본에서 규격이탈=Y 행 → LOT·시간·설비 열 추적",
        })
    return pd.DataFrame(rows)


def build_subgroup_trace_table(
    sample_df: pd.DataFrame,
    analysis: SpcAnalysisResult,
    decision: SpcDecisionResult | None,
) -> pd.DataFrame:
    """Subgroup별 이상·관리한계·규격 이탈 요약."""
    usl, lsl = _spec_limits_from_analysis(analysis)
    mean_ooc = _collect_mean_chart_ooc_subgroups(analysis)
    disp_ooc = collect_dispersion_violation_points(analysis)
    rule_labels = collect_point_violation_labels(decision, analysis)

    sg_stats = analysis.subgroup_stats
    rows: list[dict[str, Any]] = []

    if analysis.chart_type == "imr" and analysis.individual_stats is not None:
        df = analysis.individual_stats
        values = sample_df["value"].astype(float).tolist() if "value" in sample_df.columns else []
        for _, srow in df.iterrows():
            pid = int(srow["point"])
            val = float(srow["I"]) if not pd.isna(srow["I"]) else float("nan")
            raw_idx = pid - 1
            meas = values[raw_idx] if 0 <= raw_idx < len(values) else val
            rules = rule_labels.get(pid, [])
            spec_hit = _value_spec_violation(meas, usl, lsl) if not math.isnan(meas) else False
            flags = []
            if spec_hit:
                flags.append("규격이탈")
            if pid in mean_ooc:
                flags.append("관리한계(I)")
            if pid in disp_ooc:
                flags.append("관리한계(MR)")
            if rules:
                flags.append("이상Rule")
            rows.append({
                "Subgroup/Point": pid,
                "대표값(I)": round(val, 6) if not math.isnan(val) else None,
                "산포(MR)": round(float(srow["MR"]), 6) if "MR" in srow and not pd.isna(srow["MR"]) else None,
                "측정값(n=1)": round(meas, 6) if not math.isnan(meas) else None,
                "규격이탈": "Y" if spec_hit else "",
                "관리한계_평균": "Y" if pid in mean_ooc else "",
                "관리한계_산포": "Y" if pid in disp_ooc else "",
                "이상Rule": "Y" if rules else "",
                "Rule목록": "; ".join(rules),
                "역추적_주의": "Y" if flags else "",
                "역추적_사유": " · ".join(flags),
            })
        return pd.DataFrame(rows)

    if sg_stats is None or "subgroup" not in sg_stats.columns:
        return pd.DataFrame(columns=[
            "Subgroup/Point", "Xbar", "R/S", "군내_규격이탈수", "규격이탈", "관리한계_평균",
            "관리한계_산포", "이상Rule", "Rule목록", "역추적_주의", "역추적_사유",
        ])

    disp_col = "R" if "R" in sg_stats.columns else ("S" if "S" in sg_stats.columns else None)
    sg_values: dict[int, list[float]] = {}
    if "subgroup_id" in sample_df.columns and "value" in sample_df.columns:
        for sg, grp in sample_df.groupby("subgroup_id", sort=False):
            sg_values[int(sg)] = grp["value"].astype(float).tolist()

    for _, srow in sg_stats.iterrows():
        sg = int(srow["subgroup"])
        xbar = float(srow["Xbar"])
        disp = float(srow[disp_col]) if disp_col and not pd.isna(srow[disp_col]) else None
        vals = sg_values.get(sg, [])
        spec_count = sum(1 for v in vals if _value_spec_violation(v, usl, lsl))
        rules = rule_labels.get(sg, [])
        flags: list[str] = []
        if spec_count:
            flags.append(f"규격이탈({spec_count}건)")
        if sg in mean_ooc:
            flags.append("관리한계(Xbar)")
        if sg in disp_ooc:
            flags.append("관리한계(R/S)")
        if rules:
            flags.append("이상Rule")
        rows.append({
            "Subgroup/Point": sg,
            "Xbar": round(xbar, 6),
            "R/S": round(disp, 6) if disp is not None else None,
            "군내_규격이탈수": spec_count,
            "규격이탈": "Y" if spec_count else "",
            "관리한계_평균": "Y" if sg in mean_ooc else "",
            "관리한계_산포": "Y" if sg in disp_ooc else "",
            "이상Rule": "Y" if rules else "",
            "Rule목록": "; ".join(rules),
            "역추적_주의": "Y" if flags else "",
            "역추적_사유": " · ".join(flags),
        })
    return pd.DataFrame(rows)


def build_traceable_sample_dataframe(
    sample_df: pd.DataFrame,
    analysis: SpcAnalysisResult,
    decision: SpcDecisionResult | None,
) -> pd.DataFrame:
    """채취표본 + 행별 역추적 플래그."""
    if sample_df is None or sample_df.empty:
        return pd.DataFrame()

    out = sample_df.copy().reset_index(drop=True)
    out.insert(0, "행번호", range(1, len(out) + 1))
    usl, lsl = _spec_limits_from_analysis(analysis)
    mean_ooc = _collect_mean_chart_ooc_subgroups(analysis)
    disp_ooc = collect_dispersion_violation_points(analysis)
    rule_labels = collect_point_violation_labels(decision, analysis)
    chart = analysis.chart_type

    spec_flags: list[str] = []
    mean_flags: list[str] = []
    disp_flags: list[str] = []
    rule_flags: list[str] = []
    rule_lists: list[str] = []
    caution: list[str] = []
    reasons: list[str] = []

    for i, row in out.iterrows():
        row_no = i + 1
        val = float(row["value"]) if "value" in out.columns and pd.notna(row["value"]) else float("nan")
        if chart in ("xbar_s", "xbar_r") and "subgroup_id" in out.columns:
            sg = int(row["subgroup_id"])
        else:
            sg = row_no

        spec_hit = _value_spec_violation(val, usl, lsl) if not math.isnan(val) else False
        mean_hit = sg in mean_ooc
        disp_hit = sg in disp_ooc
        rules = rule_labels.get(sg, [])
        parts: list[str] = []
        if spec_hit:
            parts.append("규격이탈")
        if mean_hit:
            parts.append("관리한계_평균" if chart != "imr" else "관리한계_I")
        if disp_hit:
            parts.append("관리한계_산포" if chart != "imr" else "관리한계_MR")
        if rules:
            parts.append("이상Rule")

        spec_flags.append("Y" if spec_hit else "")
        mean_flags.append("Y" if mean_hit else "")
        disp_flags.append("Y" if disp_hit else "")
        rule_flags.append("Y" if rules else "")
        rule_lists.append("; ".join(rules))
        caution.append("Y" if parts else "")
        reasons.append(" · ".join(parts))

    out["역추적_주의"] = caution
    out["규격이탈"] = spec_flags
    out["관리한계_평균차트"] = mean_flags
    out["관리한계_산포차트"] = disp_flags
    out["이상Rule"] = rule_flags
    out["Rule목록"] = rule_lists
    out["역추적_사유"] = reasons
    if "subgroup_id" in out.columns:
        out["Subgroup"] = out["subgroup_id"]
    elif chart == "imr":
        out["Subgroup"] = out["행번호"]
    return out


def build_traceability_sheets(
    sample_df: pd.DataFrame,
    analysis: SpcAnalysisResult,
    decision: SpcDecisionResult | None,
) -> list[tuple[str, pd.DataFrame]]:
    """종합 Excel용 역추적 시트 목록."""
    sheets: list[tuple[str, pd.DataFrame]] = [
        ("역추적_요약", build_capability_trace_summary(decision, analysis)),
        ("역추적_Subgroup", build_subgroup_trace_table(sample_df, analysis, decision)),
        ("역추적_채취표본", build_traceable_sample_dataframe(sample_df, analysis, decision)),
    ]
    if decision is not None:
        anomaly = build_anomaly_point_table(decision, analysis)
        if not anomaly.empty:
            sheets.append(("역추적_이상점", anomaly))
    return sheets
