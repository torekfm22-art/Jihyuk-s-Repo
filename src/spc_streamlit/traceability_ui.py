"""관리도 해석 — Raw Value 차트 · 데이터 추적 현황."""
from __future__ import annotations

import importlib

import pandas as pd
import streamlit as st

from src.spc import interactive_charts as _interactive_charts

importlib.reload(_interactive_charts)

from src.spc.chart_violations import (
    collect_chart_violation_points,
    collect_dispersion_violation_points,
    collect_point_violation_labels,
    expand_violation_row_indices,
)
from src.spc.decision_models import SpcDecisionResult
from src.spc.pipeline import SpcPipelineResult
from src.spc.sample_ordering import sort_sample_dataframe
from src.spc.statistics import SpcAnalysisResult
from src.spc.traceability_export import (
    build_subgroup_trace_table,
    build_traceable_sample_dataframe,
)


def _collect_anomaly_subgroups(
    analysis: SpcAnalysisResult,
    decision: SpcDecisionResult | None,
) -> set[int]:
    points = collect_chart_violation_points(decision, analysis)
    points.update(collect_dispersion_violation_points(analysis))
    return points


def _style_anomaly_rows(display_df: pd.DataFrame, anomaly_mask: pd.Series) -> pd.io.formats.style.Styler:
    pink = "background-color: #ffc0cb"

    def _highlight(row: pd.Series):
        if bool(anomaly_mask.iloc[row.name]):
            return [pink] * len(row)
        return [""] * len(row)

    return display_df.style.apply(_highlight, axis=1)


def _prepare_trace_context(
    active: SpcPipelineResult,
    analysis: SpcAnalysisResult,
    decision: SpcDecisionResult,
):
    sample_df = active.sample_df
    if sample_df is None or sample_df.empty:
        return None

    sorted_sample = sort_sample_dataframe(sample_df)
    anomaly_subgroups = _collect_anomaly_subgroups(analysis, decision)
    rule_labels = collect_point_violation_labels(decision, analysis)
    row_positions = expand_violation_row_indices(
        sorted_sample,
        anomaly_subgroups,
        analysis.chart_type,
    )
    sg_table = build_subgroup_trace_table(sorted_sample, analysis, decision)
    trace_df = build_traceable_sample_dataframe(sorted_sample, analysis, decision)
    is_xbar = analysis.chart_type in ("xbar_s", "xbar_r")
    sg_label = "Subgroup" if is_xbar else "Point"

    return {
        "sorted_sample": sorted_sample,
        "anomaly_subgroups": anomaly_subgroups,
        "rule_labels": rule_labels,
        "row_positions": row_positions,
        "sg_table": sg_table,
        "trace_df": trace_df,
        "sg_label": sg_label,
    }


def render_raw_value_chart_section(
    active: SpcPipelineResult,
    analysis: SpcAnalysisResult,
    decision: SpcDecisionResult,
) -> dict | None:
    """Raw Value Chart + 하단 이상 Subgroup 추적(expander)."""
    ctx = _prepare_trace_context(active, analysis, decision)
    if ctx is None:
        st.warning("채취 표본이 없어 Raw Value Chart를 표시할 수 없습니다.")
        return None

    st.subheader("Raw Value Chart")
    st.caption(
        "측정값은 **시간순(왼→오)** 으로 나열됩니다. x축 눈금은 **월/일 시:분** 형식이며, "
        "점에 마우스를 올리면 **일시 · LOT · 측정값 · Subgroup** 등이 팝업으로 표시됩니다."
    )

    cap = analysis.capability
    mean_val = float(cap.mean) if cap else None
    fig = _interactive_charts.build_traceability_raw_chart_figure(
        ctx["sorted_sample"],
        mean=mean_val,
        violation_points=ctx["row_positions"],
        anomaly_subgroups=ctx["anomaly_subgroups"],
        rule_labels_by_point=ctx["rule_labels"],
        chart_type=analysis.chart_type,
    )
    if fig is not None:
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Raw Value 차트를 생성할 수 없습니다.")

    sg_label = ctx["sg_label"]
    sg_table = ctx["sg_table"]
    anomaly_subgroups = ctx["anomaly_subgroups"]

    with st.expander("이상 Subgroup 추적", expanded=False):
        st.caption("분홍 **SG n** 라벨은 Raw Value Chart에서 이상이 탐지된 Subgroup입니다.")
        if anomaly_subgroups:
            flagged_txt = ", ".join(f"**{sg_label} {sg}**" for sg in sorted(anomaly_subgroups))
            st.warning(f"이상 {sg_label} ({len(anomaly_subgroups)}개): {flagged_txt}")
            if not sg_table.empty and "역추적_사유" in sg_table.columns:
                reason_rows = sg_table.loc[
                    sg_table["역추적_주의"] == "Y",
                    ["Subgroup/Point", "역추적_사유", "Rule목록"],
                ]
                if not reason_rows.empty:
                    st.dataframe(reason_rows, hide_index=True, use_container_width=True)
        else:
            st.success(f"탐지된 이상 {sg_label} 없음 — 관리도 기준 관리상태")

    return ctx


def render_data_trace_status(ctx: dict) -> None:
    """데이터 추적 현황 — 이상 행 분홍 음영."""
    sorted_sample = ctx["sorted_sample"]
    trace_df = ctx["trace_df"]
    anomaly_subgroups = ctx["anomaly_subgroups"]
    sg_label = ctx["sg_label"]

    st.divider()
    st.subheader("데이터 추적 현황")
    st.caption("이상점·규격이탈·관리한계 이탈이 있는 행은 **분홍색**으로 표시됩니다.")

    display_df = sorted_sample.copy().reset_index(drop=True)
    anomaly_mask = (trace_df["역추적_주의"] == "Y").reset_index(drop=True)
    n_anomaly = int(anomaly_mask.sum())
    c1, c2, c3 = st.columns(3)
    c1.metric("전체 행", len(display_df))
    c2.metric("이상 행", n_anomaly)
    c3.metric(f"이상 {sg_label} 수", len(anomaly_subgroups))

    if n_anomaly > 0:
        styled = _style_anomaly_rows(display_df, anomaly_mask)
        st.dataframe(styled, use_container_width=True, height=420)
    else:
        st.dataframe(display_df, use_container_width=True, height=420)

    with st.expander("역추적 플래그 열 포함 (Excel 내보내기 형식)", expanded=False):
        st.dataframe(trace_df, use_container_width=True, height=360)


def render_stability_trace_sections(
    active: SpcPipelineResult,
    analysis: SpcAnalysisResult,
    decision: SpcDecisionResult,
) -> None:
    """Raw Value Chart + 데이터 추적 현황."""
    ctx = render_raw_value_chart_section(active, analysis, decision)
    if ctx is not None:
        render_data_trace_status(ctx)
