"""Streamlit — 데이터 검증 Excel 생성 (프로그램 vs 수식 비교)."""
from __future__ import annotations

import io
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
from openpyxl import Workbook

from src.spc.comprehensive_report import ComprehensiveReportGenerator
from src.spc.constants import A2, A3, B3, B4, C4, D2, D3, D4, I_MR_D2, I_MR_D4
from src.spc.decision_models import SpcDecisionResult
from src.spc.non_normal_validation import (
    excel_non_normal_pp_formula,
    excel_non_normal_ppk_formula,
    non_normal_metrics_from_values,
)
from src.spc.report_validation_sheet import add_validation_sheet, sanitize_xlsx_formula_file
from src.spc.statistics import SpcAnalysisResult


def build_validation_workbook_bytes(
    analysis: SpcAnalysisResult,
    sample_df: pd.DataFrame,
    decision: SpcDecisionResult | None = None,
) -> bytes:
    """검증_수식연계 시트가 포함된 Excel 바이트 생성."""
    wb = Workbook()
    if wb.active:
        wb.remove(wb.active)

    gen = ComprehensiveReportGenerator(Path(tempfile.gettempdir()))
    registry = gen._add_detail_sheets(wb, analysis, sample_df, decision)
    add_validation_sheet(wb, analysis, registry, decision)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp_path = Path(tmp.name)
        tmp_path.write_bytes(buf.getvalue())
    sanitize_xlsx_formula_file(tmp_path)
    data = tmp_path.read_bytes()
    tmp_path.unlink(missing_ok=True)
    return data


@st.cache_data(show_spinner="검증 Excel 생성 중...")
def build_validation_workbook_cached(
    target_key: str,
    chart_type: str,
    sample_fingerprint: str,
    analysis: SpcAnalysisResult,
    sample_df: pd.DataFrame,
    decision: SpcDecisionResult | None,
) -> bytes:
    """Streamlit 캐시 — 동일 표본·대상 재생성 방지."""
    _ = (target_key, chart_type, sample_fingerprint)
    return build_validation_workbook_bytes(analysis, sample_df, decision)


def sample_data_fingerprint(sample_df: pd.DataFrame) -> str:
    """캐시 키용 표본 해시."""
    try:
        from pandas.util import hash_pandas_object

        return hash_pandas_object(sample_df, index=True).sum().__str__()
    except Exception:
        return str(len(sample_df))


def _match_status(py_val, excel_val, tol: float = 1e-4) -> str:
    if py_val is None or excel_val is None:
        return "N/A"
    try:
        return "OK" if abs(float(py_val) - float(excel_val)) < tol else "NG"
    except (TypeError, ValueError):
        return "N/A"


def _add_comparison_row(
    rows: list[dict],
    *,
    category: str,
    label: str,
    python_val,
    formula: str,
    excel_val,
    link: str = "",
    tol: float = 1e-4,
) -> None:
    diff = None
    if isinstance(python_val, (int, float)) and isinstance(excel_val, (int, float)):
        diff = abs(float(python_val) - float(excel_val))
    rows.append({
        "구분": category,
        "항목": label,
        "프로그램 산출": python_val,
        "Excel 검증 수식": formula,
        "Excel 계산값": excel_val,
        "차이": diff,
        "일치": _match_status(python_val, excel_val, tol),
        "연계": link,
    })


def _add_transform_validation_rows(
    rows: list[dict],
    decision: SpcDecisionResult | None,
) -> None:
    """정규성 변환(Box-Cox · Johnson) 검증 행."""
    if decision is None:
        return
    norm = decision.normality
    attempts = list(getattr(norm, "transform_attempts", None) or [])
    if not attempts and norm.transform_method:
        attempts = [{
            "method": norm.transform_method,
            "method_label": "Box-Cox" if norm.transform_method == "box_cox" else "Johnson SU",
            "attempted": True,
            "p_value_after": norm.transform_p_value_after,
            "lambda": None,
            "statistic_after": None,
            "success": norm.transform_success,
        }]

    for att in attempts:
        method = str(att.get("method") or "")
        label_prefix = str(att.get("method_label") or method or "변환")
        if not att.get("attempted"):
            continue
        p_after = att.get("p_value_after")
        if p_after is not None:
            _add_comparison_row(
                rows,
                category="정규성 검정",
                label=f"{label_prefix} 변환 후 p-value",
                python_val=p_after,
                formula="Shapiro-Wilk (변환 후 데이터)",
                excel_val=p_after,
                link="정규성 변환",
            )
        stat_after = att.get("statistic_after")
        if stat_after is not None:
            _add_comparison_row(
                rows,
                category="정규성 검정",
                label=f"{label_prefix} 변환 후 W 통계량",
                python_val=stat_after,
                formula="Shapiro-Wilk W (변환 후)",
                excel_val=stat_after,
                link="정규성 변환",
            )
        if method == "box_cox" and att.get("lambda") is not None:
            _add_comparison_row(
                rows,
                category="정규성 검정",
                label="Box-Cox λ (lambda)",
                python_val=att.get("lambda"),
                formula="Box-Cox MLE λ",
                excel_val=att.get("lambda"),
                link="Box-Cox 변환",
                tol=1e-5,
            )
        if method == "box_cox" and att.get("shift") is not None:
            _add_comparison_row(
                rows,
                category="정규성 검정",
                label="Box-Cox shift",
                python_val=att.get("shift"),
                formula="Box-Cox shift",
                excel_val=att.get("shift"),
                link="Box-Cox 변환",
                tol=1e-5,
            )
        if method == "johnson_su" and att.get("success"):
            _add_comparison_row(
                rows,
                category="정규성 검정",
                label="Johnson SU 변환 적용",
                python_val="Y" if att.get("success") else "N",
                formula="johnsonsu.fit + 정규분위수 변환",
                excel_val="Y" if att.get("success") else "N",
                link="Johnson SU",
            )


def build_validation_comparison_df(
    analysis: SpcAnalysisResult,
    sample_df: pd.DataFrame,
    decision: SpcDecisionResult | None = None,
) -> pd.DataFrame:
    """프로그램 산출 vs Excel 수식 동치 계산 비교표."""
    rows: list[dict] = []
    cols = ["구분", "항목", "프로그램 산출", "Excel 검증 수식", "Excel 계산값", "차이", "일치", "연계"]
    if sample_df is None or sample_df.empty or "value" not in sample_df.columns:
        return pd.DataFrame(columns=cols)

    vals = sample_df["value"].astype(float).to_numpy()
    cap = analysis.capability
    cl = analysis.control_limits
    cat_sample = "표본 통계"
    cat_chart = "관리도"
    cat_cap = "공정능력"
    cat_norm = "정규성 검정"

    _add_comparison_row(
        rows,
        category=cat_sample,
        label="표본수 n",
        python_val=analysis.normality.n,
        formula="COUNT",
        excel_val=len(vals),
        link="채취표본",
    )
    if cap:
        _add_comparison_row(
            rows,
            category=cat_sample,
            label="평균 Mean",
            python_val=cap.mean,
            formula="AVERAGE",
            excel_val=float(np.mean(vals)),
            link="채취표본",
        )
        _add_comparison_row(
            rows,
            category=cat_sample,
            label="σ_overall STDEV.S",
            python_val=cap.std_overall,
            formula="STDEV.S",
            excel_val=float(np.std(vals, ddof=1)) if len(vals) > 1 else 0.0,
            link="채취표본",
            tol=1e-5,
        )

    chart = analysis.chart_type
    n = cl.subgroup_size or 0
    if chart in ("xbar_r", "xbar_s") and analysis.subgroup_stats is not None:
        sg = analysis.subgroup_stats
        xbar = sg["Xbar"].astype(float).to_numpy()
        xbar_bar = float(np.mean(xbar))
        _add_comparison_row(
            rows,
            category=cat_chart,
            label="X̿ (Xbar-bar)",
            python_val=cl.center_line,
            formula="AVERAGE(Xbar)",
            excel_val=xbar_bar,
            link="Subgroup통계",
            tol=1e-5,
        )
        if chart == "xbar_r" and "R" in sg.columns:
            r_vals = sg["R"].astype(float).to_numpy()
            r_bar = float(np.mean(r_vals))
            _add_comparison_row(
                rows, category=cat_chart, label="R̄", python_val=cl.r_limits["CL"] if cl.r_limits else None,
                formula="AVERAGE(R)", excel_val=r_bar, link="Subgroup통계", tol=1e-5,
            )
            if n in D2:
                _add_comparison_row(
                    rows, category=cat_chart, label="σ_within=R̄/d2", python_val=cl.sigma_estimate,
                    formula=f"AVERAGE(R)/{D2[n]}", excel_val=r_bar / D2[n], tol=1e-5,
                )
            if cl.xbar_limits and n in A2:
                ucl_py = cl.xbar_limits["UCL"]
                lcl_py = cl.xbar_limits["LCL"]
                ucl_xl = xbar_bar + A2[n] * r_bar
                lcl_xl = xbar_bar - A2[n] * r_bar
                _add_comparison_row(
                    rows, category=cat_chart, label="Xbar UCL", python_val=ucl_py,
                    formula=f"AVERAGE(Xbar)+{A2[n]}*AVERAGE(R)", excel_val=ucl_xl, tol=1e-4,
                )
                _add_comparison_row(
                    rows, category=cat_chart, label="Xbar LCL", python_val=lcl_py,
                    formula=f"AVERAGE(Xbar)-{A2[n]}*AVERAGE(R)", excel_val=lcl_xl, tol=1e-4,
                )
            if cl.r_limits and n in D3 and n in D4:
                ucl_r_py = cl.r_limits["UCL"]
                lcl_r_py = cl.r_limits["LCL"]
                ucl_r_xl = D4[n] * r_bar
                lcl_r_xl = D3[n] * r_bar
                _add_comparison_row(
                    rows, category=cat_chart, label="R UCL", python_val=ucl_r_py,
                    formula=f"{D4[n]}*AVERAGE(R)", excel_val=ucl_r_xl, tol=1e-4,
                )
                _add_comparison_row(
                    rows, category=cat_chart, label="R LCL", python_val=lcl_r_py,
                    formula=f"{D3[n]}*AVERAGE(R)", excel_val=lcl_r_xl, tol=1e-4,
                )
        if chart == "xbar_s" and "S" in sg.columns:
            s_vals = sg["S"].astype(float).to_numpy()
            s_bar = float(np.mean(s_vals))
            _add_comparison_row(
                rows, category=cat_chart, label="S̄", python_val=cl.s_limits["CL"] if cl.s_limits else None,
                formula="AVERAGE(S)", excel_val=s_bar, link="Subgroup통계", tol=1e-5,
            )
            if n in C4:
                _add_comparison_row(
                    rows, category=cat_chart, label="σ_within=S̄/c4", python_val=cl.sigma_estimate,
                    formula=f"AVERAGE(S)/{C4[n]}", excel_val=s_bar / C4[n], tol=1e-5,
                )
            if cl.xbar_limits and n in A3:
                ucl_py = cl.xbar_limits["UCL"]
                lcl_py = cl.xbar_limits["LCL"]
                ucl_xl = xbar_bar + A3[n] * s_bar
                lcl_xl = xbar_bar - A3[n] * s_bar
                _add_comparison_row(
                    rows, category=cat_chart, label="Xbar UCL", python_val=ucl_py,
                    formula=f"AVERAGE(Xbar)+{A3[n]}*AVERAGE(S)", excel_val=ucl_xl, tol=1e-4,
                )
                _add_comparison_row(
                    rows, category=cat_chart, label="Xbar LCL", python_val=lcl_py,
                    formula=f"AVERAGE(Xbar)-{A3[n]}*AVERAGE(S)", excel_val=lcl_xl, tol=1e-4,
                )
            if cl.s_limits and n in B3 and n in B4:
                ucl_s_py = cl.s_limits["UCL"]
                lcl_s_py = cl.s_limits["LCL"]
                ucl_s_xl = B4[n] * s_bar
                lcl_s_xl = B3[n] * s_bar
                _add_comparison_row(
                    rows, category=cat_chart, label="S UCL", python_val=ucl_s_py,
                    formula=f"{B4[n]}*AVERAGE(S)", excel_val=ucl_s_xl, tol=1e-4,
                )
                _add_comparison_row(
                    rows, category=cat_chart, label="S LCL", python_val=lcl_s_py,
                    formula=f"{B3[n]}*AVERAGE(S)", excel_val=lcl_s_xl, tol=1e-4,
                )

    elif chart == "imr" and analysis.individual_stats is not None:
        ind = analysis.individual_stats
        i_vals = ind["I"].astype(float).to_numpy()
        i_bar = float(np.mean(i_vals))
        _add_comparison_row(
            rows, category=cat_chart, label="Ī", python_val=cl.center_line, formula="AVERAGE(I)",
            excel_val=i_bar, link="Individual통계", tol=1e-5,
        )
        mr_vals = ind["MR"].dropna().astype(float).to_numpy()
        if len(mr_vals) and cl.mr_limits:
            mr_bar = float(np.mean(mr_vals))
            _add_comparison_row(
                rows, category=cat_chart, label="MR̄", python_val=cl.mr_limits["CL"], formula="AVERAGE(MR)",
                excel_val=mr_bar, link="Individual통계", tol=1e-5,
            )
            _add_comparison_row(
                rows, category=cat_chart, label="σ_within", python_val=cl.sigma_estimate,
                formula=f"AVERAGE(MR)/{I_MR_D2}", excel_val=mr_bar / I_MR_D2, tol=1e-5,
            )
            if cl.i_limits:
                sigma_i = mr_bar / I_MR_D2
                ucl_i_xl = i_bar + 3 * sigma_i
                lcl_i_xl = i_bar - 3 * sigma_i
                _add_comparison_row(
                    rows, category=cat_chart, label="I UCL", python_val=cl.i_limits["UCL"],
                    formula=f"AVERAGE(I)+3*AVERAGE(MR)/{I_MR_D2}", excel_val=ucl_i_xl, tol=1e-4,
                )
                _add_comparison_row(
                    rows, category=cat_chart, label="I LCL", python_val=cl.i_limits["LCL"],
                    formula=f"AVERAGE(I)-3*AVERAGE(MR)/{I_MR_D2}", excel_val=lcl_i_xl, tol=1e-4,
                )
            _add_comparison_row(
                rows, category=cat_chart, label="MR UCL", python_val=cl.mr_limits["UCL"],
                formula=f"{I_MR_D4}*AVERAGE(MR)", excel_val=I_MR_D4 * mr_bar, tol=1e-4,
            )
            if cl.mr_limits.get("LCL") is not None:
                _add_comparison_row(
                    rows, category=cat_chart, label="MR LCL", python_val=cl.mr_limits["LCL"],
                    formula="0", excel_val=0.0, tol=1e-4,
                )

    if cap and cl.sigma_estimate and (cap.usl is not None or cap.lsl is not None):
        sigma = cl.sigma_estimate
        spec = cap.spec_type

        if spec == "upper_only" and cap.usl is not None:
            cpu = (cap.usl - cap.mean) / (3 * sigma)
            ppu = (cap.usl - cap.mean) / (3 * cap.std_overall)
            _add_comparison_row(
                rows, category=cat_cap, label="Cpk (CWU)", python_val=cap.cpk,
                formula="(USL-Mean)/(3σ_within)", excel_val=cpu, tol=1e-4,
            )
            _add_comparison_row(
                rows, category=cat_cap, label="Ppk (Ppu)", python_val=cap.ppk,
                formula="(USL-Mean)/(3σ_overall)", excel_val=ppu, tol=1e-4,
            )
        elif spec == "lower_only" and cap.lsl is not None:
            cpl = (cap.mean - cap.lsl) / (3 * sigma)
            ppl = (cap.mean - cap.lsl) / (3 * cap.std_overall)
            _add_comparison_row(
                rows, category=cat_cap, label="Cpk (CWL)", python_val=cap.cpk,
                formula="(Mean-LSL)/(3σ_within)", excel_val=cpl, tol=1e-4,
            )
            _add_comparison_row(
                rows, category=cat_cap, label="Ppk (Ppl)", python_val=cap.ppk,
                formula="(Mean-LSL)/(3σ_overall)", excel_val=ppl, tol=1e-4,
            )
        elif cap.usl is not None and cap.lsl is not None:
            _add_comparison_row(rows, category=cat_cap, label="Cp", python_val=cap.cp,
                                formula="(USL-LSL)/(6σ_within)", excel_val=(cap.usl - cap.lsl) / (6 * sigma), tol=1e-4)
            cpu = (cap.usl - cap.mean) / (3 * sigma)
            cpl = (cap.mean - cap.lsl) / (3 * sigma)
            _add_comparison_row(rows, category=cat_cap, label="Cpk", python_val=cap.cpk, formula="min(Cpu,Cpl)",
                                excel_val=min(cpu, cpl), tol=1e-4)
            _add_comparison_row(rows, category=cat_cap, label="Pp", python_val=cap.pp,
                                formula="(USL-LSL)/(6σ_overall)", excel_val=(cap.usl - cap.lsl) / (6 * cap.std_overall), tol=1e-4)
            ppu = (cap.usl - cap.mean) / (3 * cap.std_overall)
            ppl = (cap.mean - cap.lsl) / (3 * cap.std_overall)
            _add_comparison_row(rows, category=cat_cap, label="Ppk (정규 σ_overall)", python_val=cap.ppk, formula="min(Ppu,Ppl)",
                                excel_val=min(ppu, ppl), tol=1e-4)

        if cap.usl is not None or cap.lsl is not None:
            nn = non_normal_metrics_from_values(vals, cap.usl, cap.lsl)
            cap_dec = decision.capability if decision else None
            if cap_dec and cap_dec.non_normal_applied:
                primary_val = cap_dec.primary_kpi_value
                primary_name = cap_dec.primary_kpi
                ppk_formula = (
                    "ABS(NORM.S.INV(P≥USL))" if spec == "upper_only"
                    else "ABS(NORM.S.INV(P≤LSL))" if spec == "lower_only"
                    else "MIN(ABS(NORM.S.INV(P≤LSL)), ABS(NORM.S.INV(P≥USL)))"
                )
                pp_formula = (
                    "ABS(NORM.S.INV(P≥USL))" if spec == "upper_only"
                    else "ABS(NORM.S.INV(P≤LSL))" if spec == "lower_only"
                    else "MAX(pp_z, (USL-LSL)/spread_pct)"
                )
                if primary_name == "Ppk":
                    py_ppk = cap_dec.ppk_non_normal if cap_dec.ppk_non_normal is not None else primary_val
                    py_pp = cap_dec.pp_non_normal if cap_dec.pp_non_normal is not None else nn.pp
                    _add_comparison_row(
                        rows,
                        category=cat_cap,
                        label="Primary KPI — Ppk (Non-normal)",
                        python_val=py_ppk,
                        formula=ppk_formula,
                        excel_val=nn.ppk,
                        link="채취표본·USL/LSL",
                        tol=1e-3,
                    )
                    if py_pp is not None and not (isinstance(py_pp, float) and py_pp != py_pp):
                        _add_comparison_row(
                            rows,
                            category=cat_cap,
                            label="Pp (Non-normal 참고)",
                            python_val=py_pp,
                            formula=pp_formula,
                            excel_val=nn.pp,
                            link="PERCENTILE 0.135~99.865",
                            tol=1e-3,
                        )
                else:
                    py_cpk = cap_dec.cpk_non_normal if cap_dec.cpk_non_normal is not None else primary_val
                    py_cp = cap_dec.cp_non_normal if cap_dec.cp_non_normal is not None else nn.cp
                    _add_comparison_row(
                        rows,
                        category=cat_cap,
                        label="Primary KPI — Cpk (Non-normal)",
                        python_val=py_cpk,
                        formula="percentile side / (spread/2)",
                        excel_val=nn.cpk,
                        link="채취표본·USL/LSL",
                        tol=1e-3,
                    )
                    if py_cp is not None and not (isinstance(py_cp, float) and py_cp != py_cp):
                        _add_comparison_row(
                            rows,
                            category=cat_cap,
                            label="Cp (Non-normal 참고)",
                            python_val=py_cp,
                            formula="(USL-LSL)/spread_pct" if spec == "two_sided" else "—",
                            excel_val=nn.cp,
                            link="PERCENTILE spread",
                            tol=1e-3,
                        )
            elif cap_dec and cap_dec.primary_kpi_value is not None:
                lbl = f"Primary KPI — {cap_dec.primary_kpi}"
                ref_val = cap.cpk if cap_dec.primary_kpi == "Cpk" else cap.ppk
                _add_comparison_row(
                    rows,
                    category=cat_cap,
                    label=lbl,
                    python_val=cap_dec.primary_kpi_value,
                    formula=f"정규 {cap_dec.primary_kpi} (Primary)",
                    excel_val=ref_val,
                    link="§4 공정능력",
                    tol=1e-4,
                )

    norm = analysis.normality
    _add_comparison_row(
        rows,
        category=cat_norm,
        label="정규성 p-value",
        python_val=norm.p_value,
        formula="Shapiro-Wilk p-value",
        excel_val=norm.p_value,
        link="scipy Shapiro-Wilk",
    )
    if norm.statistic is not None:
        _add_comparison_row(
            rows,
            category=cat_norm,
            label="정규성 W 통계량",
            python_val=norm.statistic,
            formula="Shapiro-Wilk W",
            excel_val=norm.statistic,
            link="scipy Shapiro-Wilk",
            tol=1e-5,
        )
    _add_transform_validation_rows(rows, decision)

    return pd.DataFrame(rows, columns=cols)

