"""Streamlit UI 공통 컴포넌트."""
from __future__ import annotations

from pathlib import Path

import math

import numpy as np
import pandas as pd
import streamlit as st

from src.spc.control_chart_interpreter import ControlChartInterpretation
from src.spc.data_extractor import ExcelColumnPreview, SpecLimitPreview
from src.spc.decision_models import SpcDecisionResult
from src.spc.pipeline import SpcPipelineResult
from src.spc.statistics import SpcAnalysisResult


def _save_bytes_to_output(output_dir: Path, filename: str, data: bytes) -> Path:
    """output 폴더에 파일 저장 — Excel 잠금·권한 오류 시 대체 이름 또는 안내."""
    from datetime import datetime

    if not data:
        raise ValueError("저장할 데이터가 없습니다. 먼저 「생성」 버튼으로 파일을 만드세요.")

    output_dir.mkdir(parents=True, exist_ok=True)
    dest = output_dir / Path(filename).name

    try:
        dest.write_bytes(data)
        return dest.resolve()
    except PermissionError:
        alt = output_dir / f"{dest.stem}_{datetime.now().strftime('%H%M%S')}{dest.suffix}"
        alt.write_bytes(data)
        return alt.resolve()
    except OSError as exc:
        raise OSError(
            f"파일 저장 실패: '{dest.name}'. "
            "Excel 등에서 같은 파일이 열려 있으면 닫은 뒤 다시 시도하세요. "
            f"({exc})"
        ) from exc


def inject_custom_css() -> None:
    st.markdown(
        """
        <style>
        .main-header {
            font-size: 1.75rem;
            font-weight: 700;
            color: #1F4E79;
            margin-bottom: 0.25rem;
        }
        .sub-header {
            font-size: 0.95rem;
            color: #5a6a7a;
            margin-bottom: 1.5rem;
        }
        .nav-toolbar-spacer {
            margin-top: 0.35rem;
        }
        .step-badge {
            display: inline-block;
            padding: 0.35rem 0.85rem;
            border-radius: 999px;
            font-size: 0.8rem;
            font-weight: 600;
            margin-right: 0.5rem;
        }
        .badge-stable { background: #C6EFCE; color: #006100; }
        .badge-unstable { background: #FFC7CE; color: #9C0006; }
        .badge-warn { background: #FFEB9C; color: #9C6500; }
        .badge-neutral { background: #D9E2F3; color: #1F4E79; }
        .insight-box {
            background: #F5F8FC;
            border-left: 4px solid #1F4E79;
            padding: 1rem 1.25rem;
            border-radius: 0 8px 8px 0;
            margin: 1rem 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def stability_badge(is_stable: bool, company_status: str | None = None) -> str:
    if company_status == "관리상태":
        return '<span class="step-badge badge-stable">관리상태 (In Control)</span>'
    if company_status == "비관리상태":
        return '<span class="step-badge badge-unstable">비관리상태 (Out of Control)</span>'
    if is_stable:
        return '<span class="step-badge badge-stable">Stable (In Control)</span>'
    return '<span class="step-badge badge-unstable">Unstable (Out of Control)</span>'


def render_step_header(step: int, title: str, subtitle: str) -> None:
    st.markdown(f"### Step {step}. {title}")
    st.caption(subtitle)


def render_stability_hero(decision: SpcDecisionResult, interp: ControlChartInterpretation) -> None:
    stable = decision.control_chart.is_stable
    company = decision.control_chart.company_interpretation
    company_status = company.status if company else None
    st.markdown(
        f'{stability_badge(stable, company_status)}'
        f'<span class="step-badge badge-neutral">{decision.metadata.stage}</span>',
        unsafe_allow_html=True,
    )
    if company:
        color = "#006100" if company.status == "관리상태" else "#9C0006"
        st.markdown(
            f'<p style="font-size:1.1rem;font-weight:700;color:{color}">'
            f'회사 표준 판정: {company.status}</p>',
            unsafe_allow_html=True,
        )
        st.caption(company.summary_message)
    st.markdown(f'<div class="insight-box">{interp.stability_detail}</div>', unsafe_allow_html=True)


def render_we_table(decision: SpcDecisionResult) -> None:
    """회사 표준 관리도 해석 결과 테이블."""
    company = decision.control_chart.company_interpretation
    if company and company.detected_rules:
        rows = []
        for r in company.detected_rules:
            pts = r.get("matchedPoints") or r.get("matched_points") or []
            vals = r.get("matchedValues") or r.get("matched_values") or []
            val_str = ", ".join(f"{v:.4f}" for v in vals[:10]) if vals else ""
            rows.append({
                "규칙명": r.get("ruleName") or r.get("rule_name"),
                "조건": r.get("condition") or r.get("description"),
                "발생 위치": ", ".join(str(p) for p in pts[:15]) + ("…" if len(pts) > 15 else ""),
                "데이터 값": val_str,
                "해석 의미": r.get("interpretationMeaning") or r.get("interpretation") or "",
            })
        st.dataframe(rows, use_container_width=True, hide_index=True)
        if company.actions:
            st.markdown("**권고 조치**")
            for a in company.actions:
                st.markdown(f"- {a}")
        return

    if company and company.status == "관리상태":
        st.success(f"회사 표준: {company.summary_message}")
        return

    violations = decision.control_chart.western_electric_violations
    if not violations:
        st.success("회사 표준: 이상 신호 없음 (관리상태)")
        return
    rows = [
        {
            "Rule ID": v.rule_id,
            "규칙": v.rule_name,
            "발생 횟수": v.occurrence_count,
            "발생 위치 (subgroup)": ", ".join(str(p) for p in v.affected_subgroups),
        }
        for v in violations
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)


def render_dispersion_deferred_warning(decision: SpcDecisionResult) -> None:
    company = decision.control_chart.company_interpretation
    if company and company.mean_chart_deferred:
        st.error("⛔ 산포관리도 이상 → 평균관리도 신뢰 불가 (참고용만 표시)")
    elif decision.control_chart.mean_chart_status == "deferred":
        st.error("⛔ 산포관리도 이상 → 평균관리도 해석 보류 (R-chart-first)")


def render_improvement_actions(interp: ControlChartInterpretation) -> None:
    if not interp.improvement_actions:
        st.info("추가 개선 조치 없음 — 정기 모니터링 유지")
        return
    for a in sorted(interp.improvement_actions, key=lambda x: x.priority):
        with st.expander(f"**P{a.priority}** [{a.category}] {a.action}", expanded=a.priority <= 3):
            st.write(a.rationale)


def _cap_fmt(value: float | None) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "—"
    return f"{value:.3f}"


def _cap_is_valid(value: float | None) -> bool:
    return value is not None and not (isinstance(value, float) and math.isnan(value))


def _cap_metric_html(
    label: str,
    main_val: float | None,
    *,
    ref_val: float | None = None,
    invalid: bool = False,
    show_before: bool = False,
    ref_prefix: str = "",
) -> str:
    if invalid or main_val is None:
        main_txt = "Invalid"
    else:
        main_txt = f"{main_val:.3f}"

    ref_html = ""
    if ref_val is not None:
        if show_before:
            ref_html = (
                f' <span style="font-size:0.72rem;color:#888;font-weight:400;">'
                f"({_cap_fmt(ref_val)})</span>"
            )
        elif invalid:
            prefix = ref_prefix or "참고 "
            ref_html = (
                f' <span style="font-size:0.72rem;color:#888;font-weight:400;">'
                f"({prefix}{_cap_fmt(ref_val)})</span>"
            )

    return (
        f'<div style="margin-bottom:0.25rem;">'
        f'<div style="font-size:0.875rem;color:rgb(49,51,63);opacity:0.7;">{label}</div>'
        f'<div style="font-size:1.75rem;font-weight:600;line-height:1.2;">{main_txt}{ref_html}</div>'
        f"</div>"
    )


def _format_pp_ppk_summary(cap, norm) -> str:
    if cap is None or cap.pp is None or cap.ppk is None:
        return "-"
    text = f"Pp={cap.pp:.3f}, Ppk={cap.ppk:.3f}"
    if cap.capability_on_transformed:
        raw_bits: list[str] = []
        if cap.pp_raw_reference is not None:
            raw_bits.append(f"Pp={_cap_fmt(cap.pp_raw_reference)}")
        if cap.ppk_raw_reference is not None:
            raw_bits.append(f"Ppk={_cap_fmt(cap.ppk_raw_reference)}")
        if raw_bits:
            text += f" (변환 전: {', '.join(raw_bits)})"
    elif norm.non_normal_detected and not cap.capability_on_transformed:
        text += " (정규성 변환 미적용)"
    return text


def _format_cp_cpk_summary(cap) -> str:
    if cap is None:
        return "-"
    if cap.cp_cpk_valid and cap.cp is not None and cap.cpk is not None:
        text = f"Cp={cap.cp:.3f}, Cpk={cap.cpk:.3f}"
        if cap.capability_on_transformed:
            raw_bits: list[str] = []
            if cap.cp_raw_reference is not None:
                raw_bits.append(f"Cp={_cap_fmt(cap.cp_raw_reference)}")
            if cap.cpk_raw_reference is not None:
                raw_bits.append(f"Cpk={_cap_fmt(cap.cpk_raw_reference)}")
            if raw_bits:
                text += f" (변환 전: {', '.join(raw_bits)})"
        return text

    ref_bits: list[str] = []
    cp_part = "Cp=Invalid"
    cpk_part = "Cpk=Invalid"
    if cap.cp_reference is not None:
        cp_part = f"Cp=Invalid ({_cap_fmt(cap.cp_reference)})"
    if cap.cpk_reference is not None:
        cpk_part = f"Cpk=Invalid ({_cap_fmt(cap.cpk_reference)})"
    note = cap.cp_cpk_validity_note or "Invalid"
    return f"{cp_part}, {cpk_part} — {note}"


def render_capability_panel(decision: SpcDecisionResult) -> None:
    cap = decision.capability
    norm = decision.normality
    if cap is None:
        st.warning("USL/LSL 미지정 — 공정능력 미산출")
        return

    show_before = cap.capability_on_transformed
    width_invalid = not cap.cp_meaningful
    cp_invalid = width_invalid or not cap.cp_cpk_valid or not _cap_is_valid(cap.cp)
    cpk_invalid = not cap.cp_cpk_valid or not _cap_is_valid(cap.cpk)
    pp_invalid = width_invalid or not _cap_is_valid(cap.pp)
    ppk_invalid = not _cap_is_valid(cap.ppk)

    spec_note = ""
    if decision.metadata.spec_type == "upper_only":
        spec_note = "편측(상한) — Cpk=CWU, Ppk=Ppu"
    elif decision.metadata.spec_type == "lower_only":
        spec_note = "편측(하한) — Cpk=CWL, Ppk=Ppl"

    if cap.capability_on_transformed:
        method = "Box-Cox" if cap.normality_transform_method == "box_cox" else "Johnson SU"
        st.caption(
            f"**{method} 변환 후** 공정능력 (Pp → Ppk → Cp → Cpk) · "
            "괄호 안은 **변환 전** 참고값"
            + (f" · {spec_note}" if spec_note else "")
        )
    elif spec_note:
        st.caption(f"**{spec_note}** · Cp/Pp는 편측 공차에서 산출하지 않습니다")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(
            _cap_metric_html(
                "Pp",
                cap.pp if not pp_invalid else None,
                ref_val=cap.pp_raw_reference if show_before else None,
                invalid=pp_invalid,
                show_before=show_before and not pp_invalid,
            ),
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            _cap_metric_html(
                "Ppk",
                cap.ppk if not ppk_invalid else None,
                ref_val=cap.ppk_raw_reference if show_before else None,
                invalid=ppk_invalid,
                show_before=show_before and not ppk_invalid,
            ),
            unsafe_allow_html=True,
        )
    with c3:
        cp_ref = (
            cap.cp_reference if cp_invalid
            else (cap.cp_raw_reference if show_before else None)
        )
        st.markdown(
            _cap_metric_html(
                "Cp",
                cap.cp if not cp_invalid else None,
                ref_val=cp_ref,
                invalid=cp_invalid,
                show_before=show_before and not cp_invalid,
            ),
            unsafe_allow_html=True,
        )
    with c4:
        cpk_ref = (
            cap.cpk_reference if cp_invalid
            else (cap.cpk_raw_reference if show_before else None)
        )
        st.markdown(
            _cap_metric_html(
                "Cpk",
                cap.cpk if not cpk_invalid else None,
                ref_val=cpk_ref,
                invalid=cpk_invalid,
                show_before=show_before and not cp_invalid,
            ),
            unsafe_allow_html=True,
        )

    if norm.non_normal_detected and cap.non_normal_applied and not cap.capability_on_transformed:
        pct_bits: list[str] = []
        if cap.pp_non_normal is not None:
            pct_bits.append(f"Pp {_cap_fmt(cap.pp_non_normal)}")
        if cap.ppk_non_normal is not None:
            pct_bits.append(f"Ppk {_cap_fmt(cap.ppk_non_normal)}")
        if cap.cp_non_normal is not None:
            pct_bits.append(f"Cp {_cap_fmt(cap.cp_non_normal)}")
        if cap.cpk_non_normal is not None:
            pct_bits.append(f"Cpk {_cap_fmt(cap.cpk_non_normal)}")
        if pct_bits:
            st.markdown(
                f'<p style="font-size:0.78rem;color:#666;margin:0.15rem 0 0.5rem 0;">'
                f"Percentile 참고: {' · '.join(pct_bits)}</p>",
                unsafe_allow_html=True,
            )

    gap_txt = (
        f"{cap.cpk_ppk_gap:.3f}"
        if cap.cpk_ppk_gap is not None
        else "—"
    )
    st.caption(f"Cp/Cpk 유효성: **{cap.cp_cpk_validity_note}** | Gap: {gap_txt} — {cap.gap_interpretation}")
    st.info(cap.process_level)


def render_capability_correlation_guide(decision: SpcDecisionResult) -> None:
    """Pp/Ppk · Cp/Cpk 지표 해석 가이드."""
    cap = decision.capability
    norm = decision.normality
    if cap is None or cap.pp is None or cap.ppk is None:
        return

    pp, ppk = cap.pp, cap.ppk
    cp = cap.cp
    cpk = cap.cpk
    lines: list[str] = [
        "**Pp / Ppk (σ_overall · 전체 변동)**",
        f"- Pp={_cap_fmt(pp)}, Ppk={_cap_fmt(ppk)} — 장기·전체 데이터 기준 성능 지표입니다.",
    ]
    if cp is not None and cpk is not None:
        cp_gap = cp - cpk
        lines.extend([
            "",
            "**Cp / Cpk (σ_within · 단기·관리도 변동)**",
            f"- Cp={_cap_fmt(cp)}, Cpk={_cap_fmt(cpk)} — 관리도 기반 단기 산포(σ_within) 기준입니다.",
        ])
        if cp_gap < 0.01:
            lines.append("- Cp≈Cpk → 평균이 규격 중심에 가깝습니다.")
        elif cpk < cp:
            lines.append(f"- Cp−Cpk={cp_gap:.3f} → 평균 치우침으로 Cpk가 Cp보다 낮습니다.")
        if cpk is not None and ppk is not None:
            lines.extend([
                "",
                f"- Cpk−Ppk = {(cpk - ppk):.3f} — {cap.gap_interpretation or ''}",
            ])
    elif not cap.cp_cpk_valid:
        ref_cp = cap.cp_reference
        ref_cpk = cap.cpk_reference
        ref_note = ""
        if ref_cp is not None or ref_cpk is not None:
            ref_note = f" (참고: Cp={_cap_fmt(ref_cp)}, Cpk={_cap_fmt(ref_cpk)})"
        lines.extend([
            "",
            f"**Cp / Cpk** — **Invalid**{ref_note} · {cap.cp_cpk_validity_note} (Pp/Ppk 중심 평가).",
        ])

    if cap.capability_on_transformed:
        method = "Box-Cox" if cap.normality_transform_method == "box_cox" else "Johnson SU"
        lines.extend([
            "",
            f"**{method} 변환** — 위 Pp/Ppk/Cp/Cpk는 변환 후 정규 공간에서 산출한 **메인** 값입니다.",
            "변환 전 원시 값은 메트릭 아래 참고란에 표시됩니다.",
        ])
    elif norm.non_normal_detected and cap.non_normal_applied:
        pct: list[str] = []
        if cap.ppk_non_normal is not None:
            pct.append(f"Ppk {_cap_fmt(cap.ppk_non_normal)}")
        if cap.pp_non_normal is not None:
            pct.append(f"Pp {_cap_fmt(cap.pp_non_normal)}")
        if cap.cpk_non_normal is not None:
            pct.append(f"Cpk {_cap_fmt(cap.cpk_non_normal)}")
        if cap.cp_non_normal is not None:
            pct.append(f"Cp {_cap_fmt(cap.cp_non_normal)}")
        if pct:
            lines.extend([
                "",
                f"**Percentile 참고** — {' · '.join(pct)} (실제 이탈 비율·백분위 기반, 판정 보조)",
            ])

    with st.expander("Pp/Ppk · Cp/Cpk 해석 가이드", expanded=False):
        st.markdown("\n".join(lines))


def render_histogram_panel(result: SpcPipelineResult) -> None:
    """공정능력 평가용 히스토그램."""
    analysis = result.analysis
    if analysis is None or result.sample_df is None or result.sample_df.empty:
        st.info("히스토그램을 표시할 데이터가 없습니다.")
        return

    cap = analysis.capability

    try:
        from src.spc.interactive_charts import (
            build_histogram_figure,
            individual_control_limits_for_histogram,
        )
        from src.spc.sample_ordering import sort_sample_dataframe

        sorted_sample = sort_sample_dataframe(result.sample_df)
        raw = sorted_sample["value"].to_numpy(dtype=float)
        mean = float(np.mean(raw))
        std = float(np.std(raw, ddof=1)) if len(raw) > 1 else 0.0
        ucl, cl, lcl = individual_control_limits_for_histogram(analysis, raw)
        st.plotly_chart(
            build_histogram_figure(
                raw,
                mean,
                std,
                ucl=ucl,
                lcl=lcl,
                cl=cl,
                usl=cap.usl if cap else None,
                lsl=cap.lsl if cap else None,
            ),
            use_container_width=True,
        )
        st.caption("X축 범위: UCL/LCL·데이터 기준 | USL/LSL은 상단 텍스트만 표기")
    except ImportError:
        st.warning("Plotly 미설치 — 정적 히스토그램을 표시합니다.")
        if result.charts and result.charts.histogram.exists():
            st.image(str(result.charts.histogram), use_container_width=True)


def render_normality_charts(result: SpcPipelineResult) -> None:
    """정규성 검정용 정규확률도 (QQ plot)."""
    analysis = result.analysis
    if analysis is None or result.sample_df is None or result.sample_df.empty:
        return

    try:
        from src.spc.interactive_charts import build_prob_plot_figure
        from src.spc.sample_ordering import sort_sample_dataframe

        sorted_sample = sort_sample_dataframe(result.sample_df)
        raw = sorted_sample["value"].to_numpy(dtype=float)
        if len(raw) < 3:
            st.info("표본이 부족하여 정규확률도를 생성할 수 없습니다.")
            return
        st.plotly_chart(build_prob_plot_figure(raw), use_container_width=True)
    except ImportError:
        st.warning("Plotly 미설치 — `pip install plotly` 후 차트를 사용하세요.")
        if result.charts and result.charts.prob_plot.exists():
            st.image(str(result.charts.prob_plot), use_container_width=True)


def render_control_chart_panel(
    result: SpcPipelineResult,
    decision: SpcDecisionResult | None = None,
) -> None:
    """관리도 차트만 표시 (이상점 마커 포함)."""
    charts = result.charts
    analysis = result.analysis
    if charts is None and analysis is None:
        return

    from src.spc.chart_violations import collect_chart_violation_points
    from src.spc.sample_ordering import sort_sample_dataframe

    violation_points = collect_chart_violation_points(decision, analysis)
    sorted_sample = (
        sort_sample_dataframe(result.sample_df)
        if result.sample_df is not None and not result.sample_df.empty
        else result.sample_df
    )

    if violation_points:
        st.caption(
            f"🔴 **이상점 {len(violation_points)}개** — "
            f"{', '.join(str(p) for p in sorted(violation_points)[:20])}"
            + ("…" if len(violation_points) > 20 else "")
        )

    st.caption("Y축 범위: UCL/LCL·데이터 기준 | USL/LSL은 오른쪽 텍스트만 표기 (규격선 없음)")

    try:
        from src.spc.interactive_charts import build_control_chart_figure

        fig = (
            build_control_chart_figure(
                analysis, sorted_sample, violation_points, decision=decision,
            )
            if analysis
            else None
        )
        if fig:
            st.plotly_chart(fig, use_container_width=True)
        elif charts and charts.control_chart.exists():
            st.image(str(charts.control_chart), use_container_width=True)
    except ImportError:
        st.warning("Plotly 미설치 — 정적 관리도 이미지를 표시합니다.")
        if charts and charts.control_chart.exists():
            st.image(str(charts.control_chart), use_container_width=True)


def render_quantitative_insights(interp) -> None:
    """차트별 정량 해석."""
    if not interp.quantitative or not interp.quantitative.insights:
        st.info("차트별 정량 해석 데이터가 없습니다.")
        return
    for ins in interp.quantitative.insights:
        with st.expander(ins.chart_name, expanded=True):
            st.markdown(f"**정량 요약:** {ins.metric_summary}")
            if ins.anomaly_points:
                st.markdown(f"**이상 시점:** {', '.join(ins.anomaly_points)}")
            st.markdown(f"**산포/한계:** {ins.dispersion_note}")
            st.markdown(f"**전문가 해석:** {ins.expert_comment}")


def render_validation_panel(active, analysis, decision) -> None:
    """데이터 검증 — 프로그램 vs Excel 수식 비교."""
    from src.spc_streamlit.validation_export import build_validation_comparison_df

    if active.sample_df is None or active.sample_df.empty:
        st.warning("채취 표본 없음 — 검증을 수행할 수 없습니다.")
        return

    cmp_df = build_validation_comparison_df(analysis, active.sample_df, decision)
    if cmp_df.empty:
        st.info("비교할 검증 항목이 없습니다.")
        return

    cap = decision.capability if decision else None
    if cap and cap.non_normal_applied:
        st.caption(
            "**Percentile (Non-normal)** 지표는 Excel §4b에서 검증 가능하며, 화면에서는 **참고**로 표시됩니다."
        )

    ok = int((cmp_df["일치"] == "OK").sum())
    ng = int((cmp_df["일치"] == "NG").sum())
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("일치 (OK)", ok)
    c2.metric("불일치 (NG)", ng)
    c3.metric("전체", len(cmp_df))
    if "구분" in cmp_df.columns:
        c4.metric("구분", cmp_df["구분"].nunique())
    st.dataframe(cmp_df, use_container_width=True, hide_index=True)
    if ng:
        st.warning(f"{ng}개 항목이 Excel 수식 계산값과 차이가 있습니다.")
    else:
        st.success("프로그램 산출값과 Excel 수식 계산값이 모두 일치합니다.")


def render_anomaly_detail_status(
    active,
    analysis: SpcAnalysisResult,
    decision: SpcDecisionResult,
) -> None:
    """이상점 상세현황 — 변동성 순위 + 판정 기준·사유·원인 코드 + Worst 상세."""
    from src.spc.variability_review import build_variability_review, review_to_dataframe

    result = build_variability_review(
        decision,
        analysis,
        sample_df=active.sample_df,
        filtered_df=active.filtered_df,
    )

    if not result.reviews:
        st.success("표기된 이상점 없음 — 회사 표준 기준 관리상태")
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("이상점 수", len(result.reviews))
    c2.metric("Worst 선정", len(result.worst))
    if result.spec_relative_sigma is not None:
        c3.metric("σ/공차", f"{result.spec_relative_sigma:.1%}")
    else:
        c3.metric("공정 변동 지수", f"{result.process_variability_index:.1f}")

    st.caption(
        "변동성 점수 = **관리도 차트 편차**와 **산포 관리도** 중 큰 값. "
        "규칙 가중치는 합산하지 않으며, Worst 3~5는 변동성이 가장 큰 순서로 선정합니다."
    )
    st.dataframe(review_to_dataframe(result), use_container_width=True, hide_index=True)

    if result.data_quality_notes:
        with st.expander("데이터 품질 — 변동성 해석 참고"):
            for note in result.data_quality_notes:
                st.markdown(f"- {note}")

    st.markdown("#### Worst 이상점 상세")
    for i, w in enumerate(result.worst, start=1):
        title = f"#{i} {w.point_label} {w.point_id} — 변동성 {w.variability_score} ({w.priority})"
        with st.expander(title, expanded=i <= 2):
            st.markdown(f"**변동성 요약:** {w.variability_summary}")
            st.markdown(f"**점수 구성:** {w.score_breakdown}")
            if w.measurement_value is not None:
                st.markdown(f"**측정값:** `{w.measurement_value:.4f}`")
            if w.deviation_sigma is not None:
                st.markdown(f"**중심선 대비 편차:** {w.deviation_sigma:.2f}σ")
            st.markdown(f"**이상 유형:** {', '.join(w.rule_names)}")
            if w.criteria:
                st.markdown(f"**판정 기준:** {' | '.join(w.criteria)}")
            if w.reasons:
                st.markdown(f"**이상 사유:** {' | '.join(w.reasons)}")
            if w.cause_codes:
                st.markdown(f"**원인 코드:** {w.cause_codes}")

            st.markdown("**추정 원인**")
            for cause in w.likely_causes:
                st.markdown(f"- {cause}")

            st.markdown("**개선 방향**")
            for action in w.improvement_actions:
                st.markdown(f"- {action}")


def render_charts_row(
    result: SpcPipelineResult,
    decision: SpcDecisionResult | None = None,
    *,
    histogram_show_violations: bool = False,
) -> None:
    """Plotly hover 차트 (fallback: 정적 PNG)."""
    charts = result.charts
    analysis = result.analysis
    if charts is None and analysis is None:
        return

    from src.spc.chart_violations import (
        collect_chart_violation_points,
        expand_violation_row_indices,
        violation_measurement_values,
    )
    from src.spc.sample_ordering import sort_sample_dataframe

    violation_points = collect_chart_violation_points(decision, analysis)
    chart_type = analysis.chart_type if analysis else None
    sorted_sample = (
        sort_sample_dataframe(result.sample_df)
        if result.sample_df is not None and not result.sample_df.empty
        else result.sample_df
    )
    row_violations = expand_violation_row_indices(sorted_sample, violation_points, chart_type)

    if violation_points:
        st.caption(
            f"🔴 **이상점 {len(violation_points)}개** 표시됨 — "
            f"포인트: {', '.join(str(p) for p in sorted(violation_points)[:20])}"
            + ("…" if len(violation_points) > 20 else "")
        )
    else:
        st.caption("마우스를 데이터 점 위에 올리면 일시·측정값·LOT 등 상세 정보가 표시됩니다.")

    try:
        from src.spc.interactive_charts import (
            build_control_chart_figure,
            build_histogram_figure,
            build_prob_plot_figure,
            build_raw_chart_figure,
            individual_control_limits_for_histogram,
        )

        raw = None
        if sorted_sample is not None and "value" in sorted_sample.columns:
            raw = sorted_sample["value"].to_numpy(dtype=float)
        usl = analysis.capability.usl if analysis and analysis.capability else None
        lsl = analysis.capability.lsl if analysis and analysis.capability else None

        violation_values = (
            violation_measurement_values(sorted_sample, violation_points, chart_type)
            if histogram_show_violations
            else []
        )

        tab_ctrl, tab_raw, tab_hist, tab_qq = st.tabs(
            ["관리도", "개별값 시계열", "히스토그램", "정규확률도"]
        )
        with tab_ctrl:
            fig = (
                build_control_chart_figure(
                    analysis, sorted_sample, violation_points, decision=decision,
                )
                if analysis
                else None
            )
            if fig:
                st.plotly_chart(fig, use_container_width=True)
            elif charts and charts.control_chart.exists():
                st.image(str(charts.control_chart), use_container_width=True)
        with tab_raw:
            fig = build_raw_chart_figure(sorted_sample, raw, violation_points=row_violations)
            if fig:
                st.plotly_chart(fig, use_container_width=True)
            elif charts and charts.raw_chart.exists():
                st.image(str(charts.raw_chart), use_container_width=True)
        with tab_hist:
            if raw is not None and len(raw):
                mean = float(np.mean(raw))
                std = float(np.std(raw, ddof=1)) if len(raw) > 1 else 0.0
                ucl, cl, lcl = individual_control_limits_for_histogram(analysis, raw) if analysis else (None, None, None)
                st.plotly_chart(
                    build_histogram_figure(
                        raw,
                        mean,
                        std,
                        ucl=ucl,
                        lcl=lcl,
                        cl=cl,
                        usl=usl,
                        lsl=lsl,
                        violation_values=violation_values if histogram_show_violations else None,
                    ),
                    use_container_width=True,
                )
            elif charts and charts.histogram.exists():
                st.image(str(charts.histogram), use_container_width=True)
        with tab_qq:
            if raw is not None and len(raw) > 2:
                st.plotly_chart(build_prob_plot_figure(raw), use_container_width=True)
            elif charts and charts.prob_plot.exists():
                st.image(str(charts.prob_plot), use_container_width=True)
    except ImportError:
        st.warning("Plotly 미설치 — `pip install plotly` 후 hover 기능을 사용하세요.")
        if charts is None:
            return
        c1, c2 = st.columns(2)
        with c1:
            if charts.control_chart.exists():
                st.image(str(charts.control_chart), caption="해석용 관리도", use_container_width=True)
            if charts.histogram.exists():
                st.image(str(charts.histogram), caption="히스토그램", use_container_width=True)
        with c2:
            if charts.prob_plot.exists():
                st.image(str(charts.prob_plot), caption="정규확률도 (QQ)", use_container_width=True)
            if charts.raw_chart.exists():
                st.image(str(charts.raw_chart), caption="개별값 시계열", use_container_width=True)


def render_study_report_chart_grid(result: SpcPipelineResult) -> None:
    """
    AIAG/VDA 스타일 2×2 차트 그리드.
    좌상: 히스토그램 · 우상: Raw Value · 좌하: 정규성(확률도) · 우하: 관리도
    """
    analysis = result.analysis
    charts = result.charts
    if analysis is None:
        return

    st.markdown("---")
    st.subheader("SPC & Process Capability Study — 차트 종합")
    st.caption("AIAG / VDA SPC Harmonized Standard · 11~14번 차트")

    def _image_cell(path: Path | None, label: str, fallback_plotly=None) -> None:
        st.markdown(f"**{label}**")
        if path is not None and path.exists():
            st.image(str(path), use_container_width=True)
            return
        if fallback_plotly is not None:
            st.plotly_chart(fallback_plotly, use_container_width=True)
            return
        st.caption("차트를 생성할 수 없습니다.")

    plotly_ready = False
    sorted_sample = None
    raw = None
    usl = lsl = None
    try:
        from src.spc.interactive_charts import (
            build_control_chart_figure,
            build_histogram_figure,
            build_prob_plot_figure,
            build_raw_chart_figure,
            individual_control_limits_for_histogram,
        )
        from src.spc.sample_ordering import sort_sample_dataframe

        plotly_ready = True
        if result.sample_df is not None and not result.sample_df.empty:
            sorted_sample = sort_sample_dataframe(result.sample_df)
            if "value" in sorted_sample.columns:
                raw = sorted_sample["value"].to_numpy(dtype=float)
        cap = analysis.capability
        usl = cap.usl if cap else None
        lsl = cap.lsl if cap else None
    except ImportError:
        pass

    def _hist_fig():
        if not plotly_ready or raw is None or len(raw) == 0:
            return None
        mean = float(np.mean(raw))
        std = float(np.std(raw, ddof=1)) if len(raw) > 1 else 0.0
        ucl, cl, lcl = individual_control_limits_for_histogram(analysis, raw)
        return build_histogram_figure(raw, mean, std, ucl=ucl, lcl=lcl, cl=cl, usl=usl, lsl=lsl)

    def _raw_fig():
        if not plotly_ready or sorted_sample is None:
            return None
        return build_raw_chart_figure(sorted_sample, raw)

    def _prob_fig():
        if not plotly_ready or raw is None or len(raw) < 3:
            return None
        return build_prob_plot_figure(raw)

    def _ctrl_fig():
        if not plotly_ready or sorted_sample is None:
            return None
        return build_control_chart_figure(analysis, sorted_sample)

    top_l, top_r = st.columns(2)
    with top_l:
        _image_cell(
            charts.histogram if charts else None,
            "11. Histogram (히스토그램)",
            _hist_fig(),
        )
    with top_r:
        _image_cell(
            charts.raw_chart if charts else None,
            "12. Raw Value Chart (개별값)",
            _raw_fig(),
        )

    bot_l, bot_r = st.columns(2)
    with bot_l:
        _image_cell(
            charts.prob_plot if charts else None,
            "13. Normal Probability Plot (정규성 검정)",
            _prob_fig(),
        )
    with bot_r:
        _image_cell(
            charts.control_chart if charts else None,
            "14. Control Chart (관리도)",
            _ctrl_fig(),
        )


def render_sidebar_analysis_target(pipe: SpcPipelineResult) -> None:
    """사이드바 — 분석 대상(측정 포인트) 선택."""
    from src.spc.characteristic_split import format_split_label
    from src.spc_streamlit.analysis_runner import list_analysis_targets
    from src.spc_streamlit.session_context import ensure_analysis_target_options

    targets = list_analysis_targets(pipe)
    if not targets:
        return

    ensure_analysis_target_options(targets)

    split_col = pipe.split_column or ""
    labels = {t: format_split_label(t, split_col) for t in targets}
    title = "측정 포인트" if split_col == "measurement_point" else "분석 대상"

    st.sidebar.selectbox(
        title,
        options=targets,
        format_func=lambda k: labels.get(k, k),
        key="active_analysis_target",
    )


def render_active_target_banner(pipe: SpcPipelineResult, active: SpcPipelineResult) -> None:
    """현재 선택된 분석 대상 강조."""
    from src.spc.characteristic_split import format_split_label, is_measurement_point_split

    if not pipe.is_batch and not is_measurement_point_split(pipe.split_column):
        return

    split_col = pipe.split_column or ""
    label = format_split_label(active.characteristic or "-", split_col)
    n_filtered = len(active.filtered_df) if active.filtered_df is not None else 0
    n_sample = active.sample_count
    st.info(
        f"**현재 분석 대상: {label}** — "
        f"필터 후 {n_filtered}행 · 채취 {n_sample}건 기준으로 "
        f"정규성 · 관리도 · 공정능력이 산출되었습니다."
    )


def render_measurement_point_panel(pipe: SpcPipelineResult, *, show_selector: bool = True) -> None:
    """측정 포인트·항목 목록 (선택은 사이드바·active_analysis_target과 연동)."""
    from src.spc.characteristic_split import format_split_label, summarize_measurement_points
    from src.spc_streamlit.analysis_runner import list_analysis_targets

    if not pipe.is_batch:
        if pipe.split_column == "measurement_point" and pipe.filtered_df is not None:
            summary = summarize_measurement_points(pipe.filtered_df, pipe.split_column)
            if summary:
                st.subheader("측정 포인트")
                import pandas as pd
                st.dataframe(
                    pd.DataFrame(summary)[["label", "row_count", "period_start", "period_end"]],
                    hide_index=True,
                    use_container_width=True,
                )
        return

    targets = list_analysis_targets(pipe)
    if not targets:
        return

    split_col = pipe.split_column or ""
    labels = {t: format_split_label(t, split_col) for t in targets}
    if split_col == "machine":
        title = "설비 ID 목록"
    elif split_col == "measurement_point" or split_col:
        from src.spc.characteristic_split import is_measurement_point_split
        title = "측정 포인트 목록" if is_measurement_point_split(split_col) else "검사항목 목록"
    else:
        title = "검사항목 목록"
    st.subheader(title)

    current = st.session_state.get("active_analysis_target", targets[0])

    rows = []
    for child in pipe.split_results:
        if child.is_batch:
            for sub in child.split_results:
                if not sub.characteristic:
                    continue
                key = sub.characteristic
                row = {
                    "선택": "▶" if key == current else "",
                    "선택명": labels.get(key, key),
                    "원본값": key,
                    "채취 표본": sub.sample_count,
                }
                if sub.filtered_df is not None:
                    row["원본 행"] = len(sub.filtered_df)
                rows.append(row)
            continue
        if not child.characteristic:
            continue
        key = child.characteristic
        row = {
            "선택": "▶" if key == current else "",
            "선택명": labels.get(key, key),
            "원본값": key,
            "채취 표본": child.sample_count,
        }
        if child.is_batch:
            row["하위 조건"] = len(child.split_results)
        if child.filtered_df is not None:
            row["원본 행"] = len(child.filtered_df)
        rows.append(row)

    import pandas as pd
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    if show_selector and len(targets) > 1:
        st.caption("분석 대상 변경: **좌측 사이드바**에서 측정 포인트를 선택하세요.")


def render_value_extreme_panel(
    active: SpcPipelineResult,
    *,
    bundle_key: str = "default",
) -> None:
    """측정값 극단치 탐지 및 제외·포함 선택 후 재분석."""
    import pandas as pd
    import streamlit as st

    from src.spc.characteristic_split import normalize_split_value
    from src.spc.value_extreme_detection import (
        detect_value_extremes,
        filter_sample_excluding_extremes,
    )
    from src.spc_streamlit.analysis_runner import rerun_with_sample_df

    sample_df = active.sample_df
    if sample_df is None or sample_df.empty:
        return

    cap = active.analysis.capability if active.analysis else None
    usl = cap.usl if cap else None
    lsl = cap.lsl if cap else None

    target_key = normalize_split_value(active.characteristic) or bundle_key
    baseline_key = f"baseline_sample_{target_key}"

    if baseline_key not in st.session_state:
        st.session_state[baseline_key] = sample_df.copy()

    baseline_df: pd.DataFrame = st.session_state[baseline_key]
    fresh_report = detect_value_extremes(baseline_df, usl=usl, lsl=lsl)

    st.subheader("측정값 극단치 점검")
    if not fresh_report.has_extremes:
        st.success("극단치로 의심되는 측정값이 없습니다.")
        if st.session_state.get(f"extreme_exclude_{target_key}"):
            st.caption("이전에 극단값 제외 재분석이 적용되어 있었다면, 원본 표본 기준으로 다시 분석할 수 있습니다.")
        return

    st.warning(
        f"**{len(fresh_report.points)}건**의 측정값이 극단치로 탐지되었습니다. "
        "정규성·관리도 해석 전 원인(결측 0, spec 대비 이탈 등)을 확인하세요."
    )

    rows = []
    for p in fresh_report.points:
        row = {"행": p.row_index, "측정값": p.value, "사유": p.reason}
        if "timestamp" in baseline_df.columns:
            row["시간"] = baseline_df.loc[p.row_index, "timestamp"] if p.row_index in baseline_df.index else ""
        if "lot" in baseline_df.columns:
            row["LOT"] = baseline_df.loc[p.row_index, "lot"] if p.row_index in baseline_df.index else ""
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    if fresh_report.spec_near_zero:
        st.caption("규격 한계가 0 근처이므로 value=0 은 정상 범위로 판단했습니다.")

    mode_key = f"extreme_mode_{target_key}"
    current_exclude = bool(st.session_state.get(f"extreme_exclude_{target_key}", False))
    default_mode = 1 if current_exclude else 0

    mode = st.radio(
        "극단치 처리",
        ["극단치 포함하여 관리도 산출", "극단치 제외 후 관리도 산출"],
        index=default_mode,
        key=mode_key,
        horizontal=True,
    )
    exclude = mode.startswith("극단치 제외")

    if st.button("적용 — 관리도·정규성 재산출", key=f"extreme_apply_{target_key}"):
        try:
            if exclude:
                sg_size = None
                if active.sampling_config:
                    sg_size = active.sampling_config.get("subgroup_size")
                new_sample = filter_sample_excluding_extremes(
                    baseline_df,
                    fresh_report.row_indices,
                    subgroup_size=int(sg_size) if sg_size else None,
                )
                if new_sample.empty or len(new_sample) < 3:
                    st.error("극단치 제외 후 남은 표본이 부족합니다(최소 3건 필요).")
                    return
                note = f"극단치 {len(fresh_report.points)}건 제외"
            else:
                new_sample = baseline_df.copy()
                note = "극단치 포함(원본 표본)"

            bundle = st.session_state.get("bundle")
            if bundle is None:
                st.error("분석 세션이 없습니다. 1단계에서 분석을 다시 실행하세요.")
                return

            updated = rerun_with_sample_df(
                bundle,
                active,
                new_sample,
                data_source_note=note,
            )
            from src.spc_streamlit.session_context import reset_export_session_state

            reset_export_session_state()
            st.session_state.bundle = updated
            st.session_state[f"extreme_exclude_{target_key}"] = exclude
            st.success(f"재분석 완료 — {note}. 3단계 이후 결과를 확인하세요.")
            st.rerun()
        except Exception as exc:
            st.error(f"재분석 실패: {exc}")


def render_data_quality_panel(active: SpcPipelineResult) -> None:
    """데이터 품질 진단 — 정규성·시계열 해석 방해 요인."""
    from src.spc.data_quality_diagnostics import analyze_data_quality

    report = analyze_data_quality(active.sample_df, active.filtered_df)
    if not report.findings:
        return

    st.subheader("데이터 품질 · 특이사항 진단")
    if report.value_summary:
        s = report.value_summary
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("표본 n", s.get("n", "-"))
        c2.metric("고유값 수", s.get("n_unique", "-"))
        c3.metric("평균", f"{s.get('mean', 0):.4f}")
        c4.metric("표준편차", f"{s.get('std', 0):.4f}")

    for f in report.findings:
        if f.severity == "critical":
            st.error(f"**{f.title}** — {f.detail}")
        elif f.severity == "warning":
            st.warning(f"**{f.title}** — {f.detail}")
        else:
            st.info(f"**{f.title}** — {f.detail}")
        if f.evidence:
            st.caption(f"근거: {f.evidence}")

    if report.follow_up_actions:
        st.markdown("**후속 조치 권고**")
        for a in report.follow_up_actions:
            st.markdown(f"- {a}")


def _format_limit_value(v: float | None) -> str:
    if v is None:
        return ""
    if v == int(v):
        return str(int(v))
    return f"{v:g}"


def _sync_spec_manual_defaults(
    file_key: str,
    sp: SpecLimitPreview | None,
) -> None:
    """감지값 → 직접 입력 필드 초기값 (파일·감지 결과 변경 시 1회)."""
    if not sp or not sp.detected:
        return
    sig = f"{sp.lsl}:{sp.usl}:{sp.suggested_spec_mode}"
    stamp_key = f"spec_limit_sig_{file_key}"
    if st.session_state.get(stamp_key) == sig:
        return
    st.session_state[stamp_key] = sig
    if sp.lsl is not None:
        st.session_state[f"spec_lsl_manual_{file_key}"] = _format_limit_value(sp.lsl)
        st.session_state[f"spec_lsl_lower_{file_key}"] = _format_limit_value(sp.lsl)
    if sp.usl is not None:
        st.session_state[f"spec_usl_manual_{file_key}"] = _format_limit_value(sp.usl)
        st.session_state[f"spec_usl_upper_{file_key}"] = _format_limit_value(sp.usl)


def render_spec_limit_picker(
    preview: ExcelColumnPreview | None,
    *,
    file_key: str = "default",
) -> tuple[str, float | None, float | None]:
    """
    규격(공차) 자동 감지·입력 UI.
    Returns: (spec_mode_label, lsl, usl)
    """
    _MODE_MAP = {
        "both": "양측 공차",
        "upper_only": "편측 — 상한치",
        "lower_only": "편측 — 하한치",
    }
    _MODE_CHOICES = list(_MODE_MAP.values())

    st.markdown("**📏 규격(LSL / USL)**")
    sp: SpecLimitPreview | None = preview.spec_limit if preview and preview.spec_limit else None
    detected = bool(sp and sp.detected)
    has_partial = bool(sp and (sp.lsl is not None or sp.usl is not None))

    if preview is None or preview.error:
        st.caption("Excel을 업로드하면 **상한값·하한값** 열에서 LSL/USL을 자동 추천합니다.")
    elif detected:
        st.caption(
            "원본 데이터에서 규격을 찾았습니다. **자동 선정**을 권장합니다."
        )
    elif has_partial:
        st.caption(
            "일부 규격만 감지되었습니다. **직접 지정**에서 값을 확인·수정하세요."
        )
    else:
        st.caption(
            "상·하한 열(상한값·하한값·USL·LSL 등)을 찾지 못했습니다. 직접 입력하세요."
        )

    _sync_spec_manual_defaults(file_key, sp)

    mode_options = ["자동 선정", "직접 지정"] if detected else ["직접 지정"]
    limit_mode = st.radio(
        "규격 입력",
        mode_options,
        horizontal=True,
        key=f"spec_limit_mode_{file_key}",
        help="원본 Excel의 상한·하한 열 또는 동일 수치 패턴에서 자동 감지합니다.",
    )

    if limit_mode == "자동 선정" and detected and sp:
        spec_label = _MODE_MAP.get(sp.suggested_spec_mode, "양측 공차")
        parts: list[str] = []
        if sp.lsl is not None:
            src = sp.lsl_display_column or sp.lsl_column or ""
            parts.append(f"**LSL** `{sp.lsl:g}` ← `{src}`")
        if sp.usl is not None:
            src = sp.usl_display_column or sp.usl_column or ""
            parts.append(f"**USL** `{sp.usl:g}` ← `{src}`")
        st.success(" · ".join(parts))
        if sp.lsl is not None and sp.usl is not None:
            c1, c2 = st.columns(2)
            c1.metric("LSL (하한)", f"{sp.lsl:g}")
            c2.metric("USL (상한)", f"{sp.usl:g}")
        elif sp.usl is not None:
            st.metric("USL (상한)", f"{sp.usl:g}")
        else:
            st.metric("LSL (하한)", f"{sp.lsl:g}")
        return spec_label, sp.lsl, sp.usl

    if has_partial and sp:
        hints: list[str] = []
        if sp.lsl is not None:
            hints.append(f"LSL `{sp.lsl:g}` (`{sp.lsl_display_column or sp.lsl_column}`)")
        if sp.usl is not None:
            hints.append(f"USL `{sp.usl:g}` (`{sp.usl_display_column or sp.usl_column}`)")
        if hints:
            st.info("감지된 값: " + " · ".join(hints))

    default_label = (
        _MODE_MAP.get(sp.suggested_spec_mode, "양측 공차")
        if has_partial and sp
        else "양측 공차"
    )
    spec_mode = st.radio(
        "공차 유형",
        _MODE_CHOICES,
        index=_MODE_CHOICES.index(default_label) if default_label in _MODE_CHOICES else 0,
        horizontal=True,
        key=f"spec_type_manual_{file_key}",
    )

    def _parse(raw: str) -> float | None:
        s = raw.strip()
        if not s:
            return None
        try:
            return float(s)
        except ValueError:
            return None

    lsl_hint = _format_limit_value(sp.lsl if sp else None)
    usl_hint = _format_limit_value(sp.usl if sp else None)

    r1, r2 = st.columns(2)
    if spec_mode == "양측 공차":
        lsl_raw = r1.text_input(
            "LSL (하한)",
            placeholder=lsl_hint or "하한값 입력",
            key=f"spec_lsl_manual_{file_key}",
        )
        usl_raw = r2.text_input(
            "USL (상한)",
            placeholder=usl_hint or "상한값 입력",
            key=f"spec_usl_manual_{file_key}",
        )
        lsl = _parse(lsl_raw)
        usl = _parse(usl_raw)
    elif spec_mode == "편측 — 상한치":
        r1.caption("LSL — 해당 없음")
        usl_raw = r2.text_input(
            "USL (상한치)",
            placeholder=usl_hint or "상한값 입력",
            key=f"spec_usl_upper_{file_key}",
        )
        lsl = None
        usl = _parse(usl_raw)
    else:
        lsl_raw = r1.text_input(
            "LSL (하한치)",
            placeholder=lsl_hint or "하한값 입력",
            key=f"spec_lsl_lower_{file_key}",
        )
        r2.caption("USL — 해당 없음")
        lsl = _parse(lsl_raw)
        usl = None

    return spec_mode, lsl, usl


def render_value_column_picker(preview: ExcelColumnPreview) -> str | None:
    """
    측정값 후보 목록 안내 + 선택 UI.
    Returns: 선택된 열 이름 또는 None(자동 인식).
    """
    st.markdown("**📋 파일 컬럼 미리보기**")

    all_columns = list(preview.columns or [])
    manual_options = preview.resolved_manual_value_options()

    if preview.error and not all_columns:
        st.warning(f"컬럼 미리보기 실패: {preview.error}")
        manual = st.text_input("측정값 열 이름 (직접 입력)", placeholder="예: 값", key="value_col_manual")
        return manual.strip() or None

    if preview.error:
        st.warning(f"일부 미리보기 항목을 불러오지 못했습니다: {preview.error}")

    meta = f"파일: **{preview.file_name}** · 시트: `{preview.sheet}` · {preview.row_count}행"
    if len(preview.sheet_names) > 1:
        meta += f" · 시트 목록: {', '.join(preview.sheet_names[:6])}"
        if len(preview.sheet_names) > 6:
            meta += " …"
    st.caption(meta)

    candidate_set = set(preview.value_candidates or [])
    with st.expander(f"전체 컬럼 ({len(all_columns)}개)", expanded=not bool(preview.value_candidates)):
        cols_per_row = 4
        for i in range(0, len(all_columns), cols_per_row):
            row = all_columns[i : i + cols_per_row]
            st.markdown(
                " · ".join(
                    f"**`{c}`**" if c in candidate_set else f"`{c}`"
                    for c in row
                )
            )

    auto_available = bool(preview.value_candidates)
    mode_labels = ["자동 탐지", "직접 선택"]
    default_mode_idx = 0 if auto_available else 1
    pick_mode = st.radio(
        "측정값 열 지정",
        mode_labels,
        horizontal=True,
        index=default_mode_idx,
        key=f"value_col_mode_{preview.file_name}_{preview.sheet}",
        help="자동 탐지가 실패하면 **직접 선택**에서 전체 컬럼 목록을 사용하세요.",
    )

    if pick_mode == "직접 선택" or not auto_available:
        if not auto_available:
            st.warning(
                "측정값 후보를 자동 탐지하지 못했습니다. "
                "아래 **전체 컬럼 목록**에서 측정값 열을 선택하세요."
            )
        else:
            st.caption("전체 컬럼 목록에서 측정값 열을 직접 선택합니다.")

        if not manual_options:
            st.error("선택 가능한 컬럼이 없습니다. Excel 시트·헤더 행을 확인하세요.")
            manual = st.text_input("또는 열 이름 직접 입력", key="value_col_manual_fallback")
            return manual.strip() or None

        choice = st.selectbox(
            "측정값 열 선택 (전체 목록)",
            options=manual_options,
            index=0,
            key=f"value_col_manual_select_{preview.file_name}_{preview.sheet}",
            help=f"총 {len(manual_options)}개 컬럼",
        )
        st.caption("목록: " + ", ".join(f"`{c}`" for c in manual_options))
        return choice or None

    st.success(
        "측정값 **후보 열** (굵게 표시): "
        + ", ".join(f"**{c}**" for c in preview.value_candidates)
    )
    if preview.recommended_column:
        st.info(
            f"권장: **`{preview.recommended_column}`** — 아래 목록에서 선택·변경할 수 있습니다."
        )

    options: list[str] = []
    if preview.recommended_column:
        options.append(preview.recommended_column)
    for c in preview.value_candidates:
        if c not in options:
            options.append(c)
    for c in manual_options:
        if c not in options:
            options.append(c)

    choice = st.selectbox(
        "측정값 열 선택",
        options=options,
        index=0,
        key=f"value_col_select_{preview.file_name}_{preview.sheet}",
        help="권장 열을 그대로 두거나 다른 후보·전체 열로 변경할 수 있습니다.",
    )
    return choice or None


def load_manual_split_options(
    preview_path: Path,
    preview: ExcelColumnPreview,
) -> list[dict]:
    """직접 지정 UI용 — 업로드 시가 아닌 선택 시점에 항목 목록 로드."""
    cache_key = f"manual_split_{preview.file_name}_{preview.sheet}"
    if cache_key in st.session_state:
        return list(st.session_state[cache_key])

    from src.spc.characteristic_split import build_manual_split_options
    from src.spc.data_extractor import _column_rename_map, _normalize_columns
    from src.spc.excel_reader import read_excel_auto

    df = read_excel_auto(preview_path, preview.sheet)
    norm_df = _normalize_columns(df.copy())
    col_display = {v: k for k, v in _column_rename_map(df).items()}
    options = build_manual_split_options(norm_df, column_display_names=col_display)
    st.session_state[cache_key] = options
    return options


def load_composite_summary(
    preview_path: Path,
    preview: ExcelColumnPreview,
    columns: list[str],
) -> list[dict]:
    """2~5열 복합 분리 — 조합별 summary (캐시)."""
    cols = [c for c in columns if c]
    cache_key = f"composite_{preview.file_name}_{preview.sheet}_{'_'.join(cols)}"
    if cache_key in st.session_state:
        return list(st.session_state[cache_key])

    from src.spc.characteristic_split import summarize_composite_split
    from src.spc.data_extractor import _column_rename_map, _normalize_columns
    from src.spc.excel_reader import read_excel_auto

    df = read_excel_auto(preview_path, preview.sheet)
    norm_df = _normalize_columns(df.copy())
    col_display = {v: k for k, v in _column_rename_map(df).items()}
    summary = summarize_composite_split(
        norm_df, cols, display_names=col_display,
    )
    st.session_state[cache_key] = summary
    return summary


def _parse_composite_dim_count(dim_mode: str) -> int:
    from src.spc.characteristic_split import MAX_COMPOSITE_COLUMNS

    if dim_mode.startswith("1"):
        return 1
    for n in range(2, MAX_COMPOSITE_COLUMNS + 1):
        if dim_mode.startswith(str(n)):
            return n
    return 1


def _pick_split_table(
    preview: ExcelColumnPreview,
    summary: list[dict],
    *,
    caption: str,
    state_key: str,
) -> list[str]:
    if len(summary) < 2:
        if summary:
            st.caption("항목이 1개이므로 분리 없이 단일 분석합니다.")
            return [str(summary[0]["point_id"])]
        return []

    pick_df = pd.DataFrame([
        {
            "선택": False,
            "항목명": str(s["point_id"]),
            "행 수": s["row_count"],
            "시작": s.get("period_start") or "—",
            "종료": s.get("period_end") or "—",
        }
        for s in summary
    ])
    st.caption(caption)
    table_height = min(560, max(180, 38 + len(pick_df) * 35))
    edited = st.data_editor(
        pick_df,
        column_config={
            "선택": st.column_config.CheckboxColumn("선택"),
            "항목명": st.column_config.TextColumn("항목명", disabled=True),
            "행 수": st.column_config.NumberColumn("행 수", disabled=True),
            "시작": st.column_config.TextColumn("시작", disabled=True),
            "종료": st.column_config.TextColumn("종료", disabled=True),
        },
        hide_index=True,
        use_container_width=True,
        height=table_height,
        key=state_key,
    )
    selected = [
        str(row["항목명"])
        for _, row in edited.iterrows()
        if bool(row.get("선택"))
    ]
    if not selected:
        st.warning("1개 이상의 항목을 선택하세요.")
    return selected


def render_measurement_point_picker(
    preview: ExcelColumnPreview,
    *,
    preview_path: Path | None = None,
) -> tuple[str, list[str], list[str]]:
    """
    데이터 분리 UI (1열 · 2~5열 복합).
    Returns: (mode: auto|manual|none, split_columns, selected values)
    """
    st.markdown("**📍 데이터 분리**")

    auto_candidates = list(preview.measurement_point_candidates or [])
    can_manual = preview_path is not None

    if not auto_candidates and not can_manual:
        st.caption(
            "분리 가능한 구분 열(설비 ID·품목·네트 갯수 등)이 없습니다. "
            "단일 데이터로 분석합니다."
        )
        return "none", [], []

    point_mode = st.radio(
        "분석 방식",
        ["자동 선정", "직접 지정", "분리 안 함 (전체 통합)"],
        horizontal=True,
        key=f"mp_point_mode_{preview.file_name}",
    )

    if point_mode == "분리 안 함 (전체 통합)":
        return "none", [], []

    dim_mode = st.radio(
        "분리 축",
        [
            "1개 열",
            "2개 열 (복합)",
            "3개 열 (복합)",
            "4개 열 (복합)",
            "5개 열 (복합)",
        ],
        horizontal=True,
        key=f"mp_dim_mode_{preview.file_name}",
        help=(
            "복합: 설비 × 품목 × 측정포인트 × 교대 × LOT 등 **조합**별 분석 "
            "(예: `EQ-01 · 품번A · 1 · 주간 · L001`)"
        ),
    )
    n_composite = _parse_composite_dim_count(dim_mode)
    composite = n_composite >= 2

    if point_mode == "직접 지정":
        if preview_path is None:
            st.warning("파일 경로를 확인할 수 없어 직접 지정 목록을 불러오지 못했습니다.")
            return "none", [], []
        with st.spinner("원본 데이터 항목 목록 불러오는 중…"):
            manual_options = load_manual_split_options(preview_path, preview)
        if composite:
            return _render_manual_composite_picker(
                preview, preview_path, manual_options, n_columns=n_composite,
            )
        return _render_manual_measurement_point_picker(preview, manual_options)

    if composite:
        if preview_path is None:
            st.warning("복합 분리는 파일 업로드 후 사용할 수 있습니다.")
            return "none", [], []
        with st.spinner("복합 조합 목록 준비 중…"):
            manual_options = load_manual_split_options(preview_path, preview)
        return _render_auto_composite_picker(
            preview, preview_path, manual_options, n_columns=n_composite,
        )

    if not auto_candidates:
        st.warning("자동 선정 가능한 구분 열이 없습니다. **직접 지정**을 사용하세요.")
        return "none", [], []

    mode, col, vals = _render_auto_measurement_point_picker(preview, auto_candidates)
    return mode, col, vals


def _render_manual_composite_picker(
    preview: ExcelColumnPreview,
    preview_path: Path,
    manual_options: list[dict],
    *,
    n_columns: int = 2,
) -> tuple[str, list[str], list[str]]:
    from src.spc.characteristic_split import MAX_COMPOSITE_COLUMNS, recommend_composite_columns

    n_columns = max(2, min(n_columns, MAX_COMPOSITE_COLUMNS))
    if not manual_options:
        st.warning("직접 지정할 수 있는 구분 열이 없습니다.")
        return "none", [], []
    if len(manual_options) < n_columns:
        st.warning(f"{n_columns}열 복합 분리에는 구분 열이 {n_columns}개 이상 필요합니다.")
        return "none", [], []

    col_labels = [str(o["display_column"]) for o in manual_options]
    col_map = {str(o["display_column"]): str(o["column"]) for o in manual_options}
    rec = recommend_composite_columns(manual_options, n_columns=n_columns) or []

    default_indices = list(range(min(n_columns, len(col_labels))))
    for i, col_id in enumerate(rec[:n_columns]):
        for j, lbl in enumerate(col_labels):
            if col_map[lbl] == col_id:
                default_indices[i] = j
                break

    pick_cols = st.columns(n_columns)
    selected_labels: list[str] = []
    for i in range(n_columns):
        with pick_cols[i]:
            selected_labels.append(
                st.selectbox(
                    f"{i + 1}차 구분 열",
                    col_labels,
                    index=default_indices[i],
                    key=f"mp_comp_{i}_{preview.file_name}_{n_columns}",
                )
            )
    split_cols = [col_map[lbl] for lbl in selected_labels]
    if len(set(split_cols)) < n_columns:
        st.error(f"서로 다른 {n_columns}개 열을 선택하세요.")
        return "none", [], []

    label_join = " × ".join(selected_labels)
    summary = load_composite_summary(preview_path, preview, split_cols)
    if len(summary) < 2:
        pid = [str(summary[0]["point_id"])] if summary else []
        return "none", split_cols, pid

    if n_columns >= 4 and len(summary) > 12:
        st.caption(
            f"{n_columns}열 복합 — 전체 **{len(summary)}**개 조합. "
            "행 수가 적은 조합은 분석 시 건너뛸 수 있습니다."
        )

    selected = _pick_split_table(
        preview,
        summary,
        caption=(
            f"**{label_join}** — 복합 조합 **{len(summary)}**개 "
            "(분석할 조합만 체크)"
        ),
        state_key=f"mp_comp_pick_{preview.file_name}_{'_'.join(split_cols)}",
    )
    return "manual", split_cols, selected


def _render_auto_composite_picker(
    preview: ExcelColumnPreview,
    preview_path: Path,
    manual_options: list[dict],
    *,
    n_columns: int = 2,
) -> tuple[str, list[str], list[str]]:
    from src.spc.characteristic_split import (
        COMPOSITE_SPLIT_COLUMN,
        MAX_COMPOSITE_COLUMNS,
        apply_composite_split_column,
        recommend_composite_columns,
        select_auto_measurement_point_values,
    )
    from src.spc.data_extractor import _normalize_columns
    from src.spc.excel_reader import read_excel_auto

    n_columns = max(2, min(n_columns, MAX_COMPOSITE_COLUMNS))
    rec = recommend_composite_columns(manual_options, n_columns=n_columns)
    if not rec or len(rec) < n_columns:
        st.warning(f"{n_columns}열 복합 분리에 사용할 열이 부족합니다.")
        return "none", [], []

    split_cols = rec[:n_columns]
    display = {str(o["column"]): str(o["display_column"]) for o in manual_options}
    labels = [display.get(c, c) for c in split_cols]
    label_join = " × ".join(labels)

    df = read_excel_auto(preview_path, preview.sheet)
    norm_df = _normalize_columns(df.copy())
    work = apply_composite_split_column(norm_df, split_cols)
    auto_vals = select_auto_measurement_point_values(work, COMPOSITE_SPLIT_COLUMN)
    summary = load_composite_summary(preview_path, preview, split_cols)
    all_ids = [str(s["point_id"]) for s in summary]

    st.info(
        f"**자동 ({label_join} 복합)** — "
        f"데이터량 기준 **{len(auto_vals)}개** 선정 (전체 {len(all_ids)}개 조합)\n\n"
        + "\n".join(f"- {v}" for v in auto_vals)
    )
    if n_columns >= 4 and len(all_ids) > 8:
        st.caption(
            f"{n_columns}열 조합이 많을 때는 **직접 지정**으로 필요한 조합만 선택하는 것을 권장합니다."
        )
    if len(all_ids) < 2:
        return "auto", split_cols, all_ids[:1]
    return "auto", split_cols, auto_vals


def _render_manual_measurement_point_picker(
    preview: ExcelColumnPreview,
    manual_options: list[dict],
) -> tuple[str, list[str], list[str]]:
    """직접 지정 — 1열."""
    if not manual_options:
        st.warning("직접 지정할 수 있는 구분 열이 없습니다.")
        return "none", [], []

    col_labels = [str(o["display_column"]) for o in manual_options]
    col_map = {str(o["display_column"]): str(o["column"]) for o in manual_options}

    col_label = st.selectbox(
        "구분 열 선택 (원본 컬럼명)",
        options=col_labels,
        key=f"mp_manual_col_{preview.file_name}",
    )
    active_col = col_map[col_label]
    active = next(o for o in manual_options if o["column"] == active_col)
    summary = list(active.get("summary") or [])

    if len(summary) < 2:
        return "none", [active_col], [str(summary[0]["point_id"])] if summary else []

    selected = _pick_split_table(
        preview,
        summary,
        caption=f"**{col_label}** — 원본 **{len(summary)}**개 항목 (체크하여 선택)",
        state_key=f"mp_manual_pick_{preview.file_name}_{active_col}",
    )
    return "manual", [active_col], selected


def _render_auto_measurement_point_picker(
    preview: ExcelColumnPreview,
    candidates: list[dict],
) -> tuple[str, list[str], list[str]]:
    """자동 선정 — 점수 기반 열 추천 + 데이터량 상위 항목."""
    from src.spc.characteristic_split import point_picker_option_map

    if not candidates:
        st.warning("자동 선정 가능한 구분 열이 없습니다. 직접 지정을 사용하세요.")
        return "none", [], []

    recommended = preview.measurement_point_column or candidates[0]["column"]
    col_labels: list[str] = []
    col_map: dict[str, str] = {}
    for i, cand in enumerate(candidates):
        col = str(cand["column"])
        display_col = str(cand.get("display_column") or col)
        if col == recommended and i == 0:
            label = f"자동 ({display_col} 추천)"
        else:
            label = display_col
        col_labels.append(label)
        col_map[label] = col

    col_label = st.selectbox(
        "측정 포인트 구분 열",
        options=col_labels,
        key=f"mp_col_{preview.file_name}",
        help="점수 기반 자동 추천 열입니다.",
    )
    active_col = col_map[col_label]
    active = next(c for c in candidates if c["column"] == active_col)
    active_display = str(active.get("display_column") or active_col)
    summary = list(active.get("summary") or [])
    all_ids = [str(s["point_id"]) for s in summary]
    auto_vals = list(active.get("auto_values") or [])
    option_map = point_picker_option_map(summary, active_col)

    if len(all_ids) < 2:
        st.caption("포인트가 1개이므로 분리 없이 단일 분석합니다.")
        return "auto", [active_col], all_ids[:1]

    auto_labels = [label for label, pid in option_map.items() if pid in auto_vals]
    if len(all_ids) > len(auto_vals):
        st.info(
            f"**자동 ({active_display} 추천)** — 데이터량 기준 **{len(auto_vals)}개** 선정 "
            f"(전체 {len(all_ids)}개)\n\n"
            + "\n".join(f"- {name}" for name in auto_labels)
        )
    else:
        st.caption(
            f"**자동 ({active_display} 추천)**\n\n"
            + "\n".join(f"- {name}" for name in auto_labels)
        )
    return "auto", [active_col], auto_vals


def render_normality_panel(analysis: SpcAnalysisResult, decision: SpcDecisionResult) -> None:
    from src.spc.rule_engine import infer_normality_label

    norm = analysis.normality
    nd = decision.normality
    c1, c2, c3 = st.columns(3)
    c1.metric("검정", norm.test_name)
    c2.metric("p-value", f"{norm.p_value:.4f}" if np.isfinite(norm.p_value) else "N/A")
    verdict = infer_normality_label(nd.normality_state)
    if nd.normality_state == "normal" and norm.is_normal:
        c3.metric("판정", "정규")
    elif nd.normality_state == "undetermined":
        c3.metric("판정", "판정불가")
    else:
        c3.metric("판정", verdict.split(" (")[0])

    if nd.non_normal_detected:
        st.info(
            "정규성 미충족 — **정규성 변환 결과**는 페이지 하단에서 확인하세요."
        )

    qq_msg = nd.qqplot_assessment.get("message")
    if qq_msg:
        st.caption(f"QQ plot: {qq_msg}")
    if nd.applied_action:
        st.warning(nd.applied_action)
    st.write(nd.handling_recommendation)


def _transform_verdict_label(is_normal_after: bool | None) -> str:
    if is_normal_after is True:
        return "정규"
    if is_normal_after is False:
        return "비정규"
    return "—"


def render_normality_transform_result(
    analysis: SpcAnalysisResult,
    decision: SpcDecisionResult,
) -> None:
    """비정규 판정 시 Box-Cox / Johnson 변환 후 정규성 만족 여부."""
    import pandas as pd

    norm = analysis.normality
    nd = decision.normality
    show = (not norm.is_normal) or nd.non_normal_detected
    if not show:
        return

    st.subheader("정규성 변환 결과")
    st.caption(
        f"원 데이터 {norm.test_name}: p={norm.p_value:.4f} → **비정규**. "
        "Box-Cox → Johnson SU 순으로 변환 후 동일 검정으로 정규성을 재확인합니다."
    )

    cap = analysis.capability
    if cap is None or (cap.usl is None and cap.lsl is None):
        st.warning(
            "USL/LSL이 없어 Box-Cox·Johnson 변환 및 변환 후 정규성 검정을 수행하지 않았습니다. "
            "규격을 지정하면 변환 결과를 확인할 수 있습니다."
        )
        return

    attempts = nd.transform_attempts
    if not attempts:
        st.info("변환 시도 결과가 없습니다. 분석을 다시 실행해 주세요.")
        return

    rows: list[dict[str, str]] = []
    for att in attempts:
        method_label = att.get("method_label") or att.get("method", "—")
        if not att.get("attempted"):
            rows.append({
                "변환 방법": method_label,
                "시도": "불가",
                "변환 후 p-value": "—",
                "변환 후 판정": "—",
                "선정": "—",
                "비고": att.get("notes") or "—",
            })
            continue
        p_after = att.get("p_value_after")
        p_txt = f"{p_after:.4f}" if p_after is not None and np.isfinite(p_after) else "N/A"
        selected = att.get("selected")
        rows.append({
            "변환 방법": method_label,
            "시도": "완료",
            "변환 후 p-value": p_txt,
            "변환 후 판정": _transform_verdict_label(att.get("is_normal_after")),
            "선정": "✓ 적용" if selected else ("—" if att.get("success") else "미선정"),
            "비고": _transform_attempt_note(att),
        })

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    if nd.transform_success:
        method = "Box-Cox" if nd.transform_method == "box_cox" else "Johnson SU"
        p_after = (
            f"{nd.transform_p_value_after:.4f}"
            if nd.transform_p_value_after is not None
            else "N/A"
        )
        st.success(
            f"**{method} 변환 선정** — 변환 후 p-value={p_after}, 정규성 **충족**. "
            "Step 5 공정능력 평가에서 변환 후 Pp/Ppk/Cp/Cpk를 메인으로 표시합니다."
        )
        cap_dec = decision.capability
        if cap_dec and cap_dec.capability_on_transformed:
            st.caption(
                f"변환 공간 Cpk={cap_dec.cpk:.3f}, Cp={cap_dec.cp:.3f} · "
                f"Ppk={cap_dec.ppk:.3f}, Pp={cap_dec.pp:.3f}"
            )
    else:
        st.error(
            "Box-Cox·Johnson 변환 후에도 정규성을 확보하지 못했습니다. "
            "Percentile 참고 지표 또는 Ppk 중심 평가를 적용합니다."
        )
        if nd.transform_summary:
            st.caption(nd.transform_summary)


def _transform_attempt_note(att: dict) -> str:
    parts: list[str] = []
    lam = att.get("lambda")
    if lam is not None:
        parts.append(f"λ={lam:.4f}")
    shift = att.get("shift")
    if shift is not None and float(shift) != 0.0:
        parts.append(f"shift={float(shift):.4g}")
    note = att.get("notes") or ""
    if note and not parts:
        return note.split(" | ")[0][:80]
    if parts:
        return ", ".join(parts)
    return "—"


def render_data_analysis_summary(result: SpcPipelineResult) -> None:
    cfg = result.sampling_config or {}
    filtered_n = len(result.filtered_df) if result.filtered_df is not None else result.raw_count
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("원본 (필터 후)", f"{filtered_n}건")
    c2.metric("채취 표본", f"{result.sample_count}건")
    c3.metric("관리도", str(cfg.get("chart_type", "-")).upper())
    c4.metric("Subgroup", f"n={cfg.get('subgroup_size', '-')}")
    c5.metric("채취 방식", result.sampling_note or "-")
    boundary_label = cfg.get("subgroup_boundary_label")
    if boundary_label:
        st.caption(
            f"Subgroup 구성 조건: **{boundary_label}** "
            f"({'자동' if cfg.get('subgroup_boundary_mode') == 'auto' else '직접 지정'})"
        )
    if cfg.get("stratified_rerun") or (
        result.sampling_note and "재구성" in str(result.sampling_note)
    ):
        st.success(
            "현재 표본은 **혼합분포 재구성** 데이터입니다. "
            "전체 합산 지표가 이전과 비슷하면 **조건별 비교표** 결과를 참고하세요."
        )
    if cfg.get("use_full_population"):
        st.caption("전수 데이터: σ_overall은 Excel STDEV.P(모집단, n) 방식으로 산출됩니다.")
    if cfg.get("sheet_name") or cfg.get("value_column"):
        st.caption(
            f"시트: {cfg.get('sheet_name', '자동')} | "
            f"측정값 열: {cfg.get('value_column') or '자동 인식'}"
        )


def render_validation_download(active, analysis, decision, builder=None) -> None:
    """하위 호환 — 데이터 검증 비교표만 표시."""
    _ = builder
    render_validation_panel(active, analysis, decision)


def render_report_downloads(result: SpcPipelineResult) -> None:
    """결론 — Excel/PDF 종합보고서 (생성 → 다운로드 / output 폴더 저장)."""
    from config.settings import OUTPUT_PATH
    from src.spc_streamlit.report_export import (
        build_comprehensive_excel,
        build_comprehensive_pdf,
        report_context,
    )

    if result.analysis is None or result.charts is None or result.sample_df is None:
        st.warning("보고서 생성에 필요한 분석 결과가 없습니다.")
        return

    ctx = report_context(result)
    target_key = str(result.characteristic or "single").replace(" ", "_").replace("#", "")
    downloads_dir = Path.home() / "Downloads"
    output_dir = Path(OUTPUT_PATH)

    st.subheader("Excel 및 PDF 종합보고서 생성")
    st.info(
        "**사용 방법**\n\n"
        "1. **「보고서 생성」** 을 누릅니다 (10~30초 소요).\n"
        "2. **「PC에 다운로드」** 를 누르면 브라우저 **다운로드** 폴더에 저장됩니다.\n"
        f"   - 일반 경로: `{downloads_dir}`\n"
        "3. 브라우저 다운로드가 안 되면 **「output 폴더에 저장」** 을 사용하세요.\n"
        f"   - 저장 경로: `{output_dir.resolve()}`\n\n"
        "**역추적 시트 (Excel)**\n"
        "- `역추적_요약` — 공정능력 미달·개선 포인트\n"
        "- `역추적_Subgroup` — 군별 관리한계·규격·Rule\n"
        "- `역추적_채취표본` — 측정 행별 표시 (분홍=주의)\n"
        "- `역추적_이상점` — Rule별 상세"
    )

    def _render_report_column(
        kind: str,
        label: str,
        mime: str,
        builder,
    ) -> None:
        bytes_key = f"{kind}_bytes_{target_key}"
        name_key = f"{kind}_name_{target_key}"
        path_key = f"{kind}_path_{target_key}"
        err_key = f"{kind}_err_{target_key}"
        save_err_key = f"{kind}_save_err_{target_key}"
        ready_key = f"{kind}_ready_{target_key}"

        if st.button(f"① {label} 생성", key=f"gen_{kind}_{target_key}", use_container_width=True):
            with st.spinner(f"{label} 생성 중…"):
                try:
                    data, fname = builder()
                    st.session_state[bytes_key] = data
                    st.session_state[name_key] = fname
                    st.session_state[ready_key] = True
                    st.session_state.pop(err_key, None)
                    st.session_state.pop(path_key, None)
                except Exception as exc:
                    st.session_state[err_key] = str(exc)
                    st.session_state.pop(ready_key, None)

        if err_key in st.session_state:
            st.error(f"{label} 생성 실패: {st.session_state[err_key]}")

        if not st.session_state.get(ready_key):
            return

        fname = st.session_state.get(name_key, f"report.{kind}")
        data = st.session_state.get(bytes_key, b"")
        size_kb = len(data) // 1024 if data else 0
        st.success(f"✅ 생성 완료 — **{fname}** ({size_kb} KB)")

        st.download_button(
            f"② {label} PC에 다운로드",
            data=data,
            file_name=fname,
            mime=mime,
            use_container_width=True,
            key=f"dl_{kind}_{target_key}",
        )

        if st.button(f"③ {label} output 폴더에 저장", key=f"save_{kind}_{target_key}", use_container_width=True):
            try:
                saved = _save_bytes_to_output(output_dir, fname, data)
                st.session_state[path_key] = str(saved)
                st.session_state.pop(save_err_key, None)
                st.rerun()
            except (OSError, ValueError, PermissionError) as exc:
                st.session_state[save_err_key] = str(exc)
                st.rerun()

        if save_err_key in st.session_state:
            st.error(f"{label} output 저장 실패: {st.session_state[save_err_key]}")

        if path_key in st.session_state:
            saved = st.session_state[path_key]
            st.markdown(f"**저장됨:** `{saved}`")
            st.caption("탐색기에서 위 경로로 이동해 파일을 열 수 있습니다.")

    c1, c2 = st.columns(2)
    with c1:
        _render_report_column(
            "excel",
            "Excel 종합보고서",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            lambda: build_comprehensive_excel(
                result.analysis,
                result.charts,
                result.sample_df,
                ctx["study_info"],
                ctx["title"],
                ctx["file_tag"],
                result.decision,
            ),
        )
    with c2:
        _render_report_column(
            "pdf",
            "PDF 종합보고서",
            "application/pdf",
            lambda: build_comprehensive_pdf(
                result.analysis,
                result.charts,
                result.sample_df,
                ctx["study_info"],
                ctx["title"],
                ctx["file_tag"],
                result.decision,
            ),
        )


def render_summary_table_download(pipe: SpcPipelineResult) -> None:
    """결론 — 분석 대상별 판정 요약표 Excel (LCL/CL/UCL·공정능력·관리도 비고)."""
    from config.settings import OUTPUT_PATH
    from src.spc.characteristic_split import format_split_label
    from src.spc.summary_table_export import iter_leaf_pipeline_results
    from src.spc_streamlit.report_export import build_multi_target_summary_excel
    from src.spc_streamlit.session_context import (
        invalidate_summary_table_if_stale,
        pipeline_export_fingerprint,
    )

    leaves = iter_leaf_pipeline_results(pipe)
    if not leaves or all(r.analysis is None for r in leaves):
        st.warning("요약표 생성에 필요한 분석 결과가 없습니다.")
        return

    downloads_dir = Path.home() / "Downloads"
    output_dir = Path(OUTPUT_PATH)
    n = len(leaves)
    tag = pipe.split_column or "summary"
    split_col = pipe.split_column or ""
    target_labels = [
        format_split_label(leaf.characteristic or "-", split_col)
        for leaf in leaves
    ]
    current_fp = pipeline_export_fingerprint(pipe)
    invalidate_summary_table_if_stale(current_fp)

    st.subheader("분석 대상별 판정 요약표 (Excel)")
    if st.session_state.pop("_summary_table_stale_notice", False):
        st.warning(
            "새 분석이 실행되어 **이전에 생성한 판정 요약표는 무효**입니다. "
            "아래 **「① 판정 요약표 생성」** 을 다시 눌러 주세요."
        )
    st.info(
        f"**{n}개** 분석 대상을 한 장의 표로 정리합니다.\n\n"
        "포함 항목: **측정항목 · LSL/USL · LCL/CL/UCL · 관리도 유형 · 판정(안정/불안정) · "
        "Pp/Ppk/Cp/Cpk · 비고**(정규성, R·X bar 관리도 해석)\n\n"
        "1. **「요약표 생성」** → 2. **「PC에 다운로드」** 또는 **output 폴더 저장**\n\n"
        f"output 저장 경로: `{output_dir.resolve()}`"
    )
    st.caption("현재 분석 대상: " + " · ".join(f"`{lbl}`" for lbl in target_labels))

    bytes_key = "summary_table_bytes"
    name_key = "summary_table_name"
    path_key = "summary_table_path"
    err_key = "summary_table_err"
    save_err_key = "summary_table_save_err"
    ready_key = "summary_table_ready"
    fp_key = "summary_table_fingerprint"

    if st.button("① 판정 요약표 생성", key="gen_summary_table", use_container_width=True):
        with st.spinner("판정 요약표 생성 중…"):
            try:
                study = pipe.study_info or (leaves[0].study_info if leaves else {})
                data, fname = build_multi_target_summary_excel(
                    pipe,
                    study_info=study,
                    file_tag=tag,
                )
                st.session_state[bytes_key] = data
                st.session_state[name_key] = fname
                st.session_state[ready_key] = True
                st.session_state[fp_key] = current_fp
                st.session_state.pop(err_key, None)
                st.session_state.pop(path_key, None)
                st.session_state.pop("_summary_table_stale_notice", None)
            except Exception as exc:
                st.session_state[err_key] = str(exc)
                st.session_state.pop(ready_key, None)

    if err_key in st.session_state:
        st.error(f"요약표 생성 실패: {st.session_state[err_key]}")

    if not st.session_state.get(ready_key):
        return

    fname = st.session_state.get(name_key, "SPC_판정요약표.xlsx")
    data = st.session_state.get(bytes_key, b"")
    size_kb = len(data) // 1024 if data else 0
    st.success(f"✅ 생성 완료 — **{fname}** ({size_kb} KB) · {n}개 대상")

    st.download_button(
        "② 판정 요약표 PC에 다운로드",
        data=data,
        file_name=fname,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        key="dl_summary_table",
    )

    if st.button("③ 판정 요약표 output 폴더에 저장", key="save_summary_table", use_container_width=True):
        try:
            saved = _save_bytes_to_output(output_dir, fname, data)
            st.session_state[path_key] = str(saved)
            st.session_state.pop(save_err_key, None)
            st.rerun()
        except (OSError, ValueError, PermissionError) as exc:
            st.session_state[save_err_key] = str(exc)
            st.rerun()

    if save_err_key in st.session_state:
        st.error(f"output 저장 실패: {st.session_state[save_err_key]}")

    if path_key in st.session_state:
        st.markdown(f"**저장됨:** `{st.session_state[path_key]}`")
        st.caption(f"일반 다운로드 경로: `{downloads_dir}`")
